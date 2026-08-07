from uuid import UUID

from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .compliance_qr import issue_wallet_qr, resolve_payment_qr
from .models import LedgerEntry, Location, Membership, Wallet
from .serializers import LedgerEntrySerializer, MoneyActionSerializer, PaymentRequestSerializer, WalletSerializer
from .services import OWNER_ROLES, STAFF_ROLES, create_payment_request, get_active_membership, post_wallet_entry, require_role


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


class SecureWalletSerializer(WalletSerializer):
    qr_token = serializers.SerializerMethodField()

    def get_qr_token(self, obj):
        return issue_wallet_qr(obj) if obj.status == Wallet.Status.ACTIVE else None


class SecureMeSerializer(serializers.Serializer):
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()
    roles = serializers.ListField(child=serializers.DictField())
    customer_wallets = SecureWalletSerializer(many=True)

    @staticmethod
    def from_user(user):
        memberships = Membership.objects.select_related("business").filter(user=user, is_active=True)
        profile = getattr(user, "member_profile", None)
        return {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "email_verified": bool(profile and profile.email_verified),
            "roles": [
                {
                    "business": item.business.name,
                    "business_slug": item.business.slug,
                    "role": item.role,
                    "can_manage_content": item.can_manage_content,
                }
                for item in memberships
            ],
            "customer_wallets": Wallet.objects.select_related(
                "business", "owner", "owner__member_profile"
            ).filter(owner=user),
        }


class SecureMoneyActionSerializer(MoneyActionSerializer):
    wallet_token = serializers.CharField(max_length=1200)


class SecureMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = SecureMeSerializer.from_user(request.user)
        return Response(SecureMeSerializer(payload).data)


class SecureMyWalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = get_object_or_404(
            Wallet.objects.select_related("business", "owner", "owner__member_profile"),
            owner=request.user,
        )
        return Response(SecureWalletSerializer(wallet).data)


class SecureStaffChargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SecureMoneyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = get_active_membership(request.user)
        if not membership or membership.role not in STAFF_ROLES:
            raise PermissionDenied

        try:
            wallet = resolve_payment_qr(data["wallet_token"], business=membership.business)
        except signing.BadSignature:
            return Response(
                {"detail": "Der Zahlungs-QR-Code ist ungültig oder abgelaufen. Bitte den aktuellen QR-Code erneut scannen."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        location = get_object_or_404(
            Location,
            pk=data.get("location_id"),
            business=membership.business,
            is_active=True,
        )
        try:
            payment = create_payment_request(
                wallet=wallet,
                location=location,
                actor=request.user,
                amount=data["amount"],
                tip_amount="0.00",
                customer_tip_required=True,
                description=data.get("description", ""),
                order_reference=data.get("order_reference", ""),
                ip_address=_client_ip(request),
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentRequestSerializer(payment).data, status=status.HTTP_202_ACCEPTED)


class SecureOwnerMoneyActionView(APIView):
    permission_classes = [IsAuthenticated]
    entry_type = LedgerEntry.Type.TOPUP

    @staticmethod
    def _resolve_owner_wallet(raw_token):
        try:
            return resolve_payment_qr(raw_token)
        except signing.BadSignature:
            try:
                legacy_token = UUID(str(raw_token))
            except (TypeError, ValueError):
                return None
            return Wallet.objects.select_related("business").filter(qr_token=legacy_token).first()

    def post(self, request):
        serializer = SecureMoneyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        wallet = self._resolve_owner_wallet(data["wallet_token"])
        if wallet is None:
            return Response({"detail": "Mitgliedskarte wurde nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
        require_role(request.user, wallet.business, OWNER_ROLES)

        location = None
        if data.get("location_id"):
            location = get_object_or_404(Location, pk=data["location_id"], business=wallet.business)
        try:
            entry = post_wallet_entry(
                wallet=wallet,
                location=location,
                entry_type=self.entry_type,
                amount=data["amount"],
                actor=request.user,
                description=data.get("description", ""),
                order_reference=data.get("order_reference", ""),
                idempotency_key=data.get("idempotency_key", ""),
                ip_address=_client_ip(request),
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class SecureManagerTopupView(SecureOwnerMoneyActionView):
    entry_type = LedgerEntry.Type.TOPUP


class SecureManagerRefundView(SecureOwnerMoneyActionView):
    entry_type = LedgerEntry.Type.REFUND
