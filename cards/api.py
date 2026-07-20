from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AppNotification, LedgerEntry, Location, PaymentRequest, PushDevice, Wallet
from .serializers import AppNotificationSerializer, LedgerEntrySerializer, LocationSerializer, MeSerializer, MoneyActionSerializer, OfferSerializer, PaymentConfirmSerializer, PaymentRequestSerializer, PushDeviceSerializer, WalletSerializer
from .services import OWNER_ROLES, STAFF_ROLES, active_offers_for, create_payment_request, finalize_payment_request, get_active_membership, post_wallet_entry, require_role


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(MeSerializer(payload).data)


class MyWalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_object_or_404(Wallet.objects.select_related("business", "owner", "owner__member_profile"), owner=request.user)
        return Response(WalletSerializer(wallet).data)


class MyTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_object_or_404(Wallet, owner=request.user)
        entries = wallet.ledger_entries.select_related("performed_by", "location")[:100]
        return Response(LedgerEntrySerializer(entries, many=True).data)


class LocationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = get_active_membership(request.user)
        wallet = Wallet.objects.filter(owner=request.user).select_related("business").first()
        business = membership.business if membership else (wallet.business if wallet else None)
        if not business:
            raise PermissionDenied
        return Response(LocationSerializer(business.locations.filter(is_active=True), many=True).data)


class OffersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_object_or_404(Wallet.objects.select_related("business"), owner=request.user)
        location = None
        location_id = request.query_params.get("location_id")
        if location_id:
            location = get_object_or_404(Location, pk=location_id, business=wallet.business, is_active=True)
        offers = active_offers_for(wallet, location)
        return Response(OfferSerializer(offers, many=True, context={"request": request}).data)


class PendingPaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_object_or_404(Wallet, owner=request.user)
        payments = wallet.payment_requests.filter(status=PaymentRequest.Status.PENDING, expires_at__gte=timezone.now()).select_related("location", "wallet")
        return Response(PaymentRequestSerializer(payments, many=True).data)


class ConfirmPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, payment_id):
        payment = get_object_or_404(PaymentRequest.objects.select_related("wallet", "location"), pk=payment_id, wallet__owner=request.user)
        serializer = PaymentConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = finalize_payment_request(payment=payment, confirmed_by=request.user, tip_percentage=serializer.validated_data["tip_percentage"], ip_address=client_ip(request))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentRequestSerializer(payment).data)


class NotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = request.user.app_notifications.select_related("location")[:100]
        return Response(AppNotificationSerializer(notifications, many=True).data)

    def post(self, request):
        notification = get_object_or_404(AppNotification, pk=request.data.get("id"), recipient=request.user)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(AppNotificationSerializer(notification).data)


class PushDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PushDeviceSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        device = serializer.save()
        return Response(PushDeviceSerializer(device).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        PushDevice.objects.filter(user=request.user, token=request.data.get("token", "")).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffChargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MoneyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = get_active_membership(request.user)
        if not membership or membership.role not in STAFF_ROLES:
            raise PermissionDenied
        wallet = get_object_or_404(Wallet.objects.select_related("business", "owner", "owner__member_profile"), business=membership.business, qr_token=data["wallet_token"])
        location = get_object_or_404(Location, pk=data.get("location_id"), business=membership.business, is_active=True)
        try:
            payment = create_payment_request(wallet=wallet, location=location, actor=request.user, amount=data["amount"], tip_percentage=data.get("tip_percentage", 0), description=data.get("description", ""), order_reference=data.get("order_reference", ""), ip_address=client_ip(request))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        code = status.HTTP_202_ACCEPTED if payment.status == PaymentRequest.Status.PENDING else status.HTTP_201_CREATED
        return Response(PaymentRequestSerializer(payment).data, status=code)


class BaseOwnerMoneyActionView(APIView):
    permission_classes = [IsAuthenticated]
    entry_type = LedgerEntry.Type.TOPUP

    def post(self, request):
        serializer = MoneyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        wallet = get_object_or_404(Wallet.objects.select_related("business"), qr_token=data["wallet_token"])
        require_role(request.user, wallet.business, OWNER_ROLES)
        location = None
        if data.get("location_id"):
            location = get_object_or_404(Location, pk=data["location_id"], business=wallet.business)
        try:
            entry = post_wallet_entry(wallet=wallet, location=location, entry_type=self.entry_type, amount=data["amount"], actor=request.user, description=data.get("description", ""), order_reference=data.get("order_reference", ""), idempotency_key=data.get("idempotency_key", ""), ip_address=client_ip(request))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class ManagerTopupView(BaseOwnerMoneyActionView):
    entry_type = LedgerEntry.Type.TOPUP


class ManagerRefundView(BaseOwnerMoneyActionView):
    entry_type = LedgerEntry.Type.REFUND
