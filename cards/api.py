from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .experience_models import TransactionCase
from .experience_services import create_transaction_case, review_transaction_case
from .models import AppNotification, LedgerEntry, Location, Membership, PaymentRequest, PushDevice, Wallet
from .serializers import AppNotificationSerializer, LedgerEntrySerializer, LocationSerializer, MeSerializer, MoneyActionSerializer, OfferSerializer, PaymentConfirmSerializer, PaymentRequestSerializer, PushDeviceSerializer, TransactionCaseCreateSerializer, TransactionCaseReviewSerializer, TransactionCaseSerializer, WalletSerializer
from .services import MANAGER_ROLES, OWNER_ROLES, STAFF_ROLES, active_offers_for, create_payment_request, finalize_payment_request, get_active_membership, post_wallet_entry, require_role


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _case_access(user, transaction_case):
    if transaction_case.wallet.owner_id == user.id:
        return True
    membership = get_active_membership(user, transaction_case.business)
    if membership and membership.role in MANAGER_ROLES:
        return True
    return bool(membership and membership.role in STAFF_ROLES and (transaction_case.opened_by_id == user.id or transaction_case.ledger_entry.performed_by_id == user.id))


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
        locations = business.locations.filter(is_active=True).select_related("visual")
        return Response(LocationSerializer(locations, many=True, context={"request": request}).data)


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
            payment = finalize_payment_request(payment=payment, confirmed_by=request.user, tip_amount=serializer.validated_data["tip_amount"], ip_address=client_ip(request))
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


class TransactionCasesView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        membership = get_active_membership(request.user)
        wallet = Wallet.objects.filter(owner=request.user).first()
        if membership and membership.role in MANAGER_ROLES:
            cases = TransactionCase.objects.filter(business=membership.business)
        elif membership and membership.role in STAFF_ROLES:
            cases = TransactionCase.objects.filter(business=membership.business).filter(Q(opened_by=request.user) | Q(ledger_entry__performed_by=request.user)).distinct()
        elif wallet:
            cases = TransactionCase.objects.filter(wallet=wallet)
        else:
            raise PermissionDenied
        cases = cases.select_related("wallet", "ledger_entry", "location", "opened_by", "reviewed_by")[:250]
        return Response(TransactionCaseSerializer(cases, many=True).data)


class TransactionCaseCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, entry_id):
        entry = get_object_or_404(LedgerEntry.objects.select_related("business", "wallet", "wallet__owner", "performed_by", "location"), pk=entry_id)
        serializer = TransactionCaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transaction_case = create_transaction_case(entry=entry, opened_by=request.user, reason=serializer.validated_data["reason"], description=serializer.validated_data["description"], requested_amount=serializer.validated_data.get("requested_amount"), ip_address=client_ip(request))
        except (DjangoValidationError, PermissionDenied) as exc:
            detail = exc.messages if isinstance(exc, DjangoValidationError) else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST if isinstance(exc, DjangoValidationError) else status.HTTP_403_FORBIDDEN)
        return Response(TransactionCaseSerializer(transaction_case).data, status=status.HTTP_201_CREATED)


class TransactionCaseDetailView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, case_id):
        transaction_case = get_object_or_404(TransactionCase.objects.select_related("business", "wallet", "ledger_entry", "ledger_entry__performed_by", "location", "opened_by", "reviewed_by"), pk=case_id)
        if not _case_access(request.user, transaction_case):
            raise PermissionDenied
        return Response(TransactionCaseSerializer(transaction_case).data)


class TransactionCaseReviewView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, case_id):
        transaction_case = get_object_or_404(TransactionCase.objects.select_related("business", "ledger_entry"), pk=case_id)
        serializer = TransactionCaseReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transaction_case = review_transaction_case(transaction_case=transaction_case, reviewer=request.user, action=serializer.validated_data["action"], manager_note=serializer.validated_data.get("manager_note", ""), approved_amount=serializer.validated_data.get("approved_amount"), ip_address=client_ip(request))
        except (DjangoValidationError, PermissionDenied) as exc:
            detail = exc.messages if isinstance(exc, DjangoValidationError) else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST if isinstance(exc, DjangoValidationError) else status.HTTP_403_FORBIDDEN)
        return Response(TransactionCaseSerializer(transaction_case).data)


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
            payment = create_payment_request(wallet=wallet, location=location, actor=request.user, amount=data["amount"], tip_amount=data.get("tip_amount", 0), description=data.get("description", ""), order_reference=data.get("order_reference", ""), ip_address=client_ip(request))
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
