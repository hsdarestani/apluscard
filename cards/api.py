from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LedgerEntry, Wallet
from .serializers import LedgerEntrySerializer, MeSerializer, MoneyActionSerializer, WalletSerializer
from .services import MANAGER_ROLES, STAFF_ROLES, post_wallet_entry, require_role


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


class MeView(APIView):
    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(MeSerializer(payload).data)


class MyWalletView(APIView):
    def get(self, request):
        wallet = get_object_or_404(Wallet.objects.select_related("business"), owner=request.user)
        return Response(WalletSerializer(wallet).data)


class MyTransactionsView(APIView):
    def get(self, request):
        wallet = get_object_or_404(Wallet, owner=request.user)
        entries = wallet.ledger_entries.select_related("performed_by")[:100]
        return Response(LedgerEntrySerializer(entries, many=True).data)


class BaseMoneyActionView(APIView):
    allowed_roles = STAFF_ROLES
    entry_type = LedgerEntry.Type.PURCHASE

    def post(self, request):
        serializer = MoneyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        wallet = get_object_or_404(Wallet.objects.select_related("business"), qr_token=data["wallet_token"])
        require_role(request.user, wallet.business, self.allowed_roles)
        try:
            entry = post_wallet_entry(
                wallet=wallet,
                entry_type=self.entry_type,
                amount=data["amount"],
                actor=request.user,
                description=data.get("description", ""),
                order_reference=data.get("order_reference", ""),
                idempotency_key=data.get("idempotency_key", ""),
                ip_address=client_ip(request),
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class StaffChargeView(BaseMoneyActionView):
    allowed_roles = STAFF_ROLES
    entry_type = LedgerEntry.Type.PURCHASE


class ManagerTopupView(BaseMoneyActionView):
    allowed_roles = MANAGER_ROLES
    entry_type = LedgerEntry.Type.TOPUP


class ManagerRefundView(BaseMoneyActionView):
    allowed_roles = MANAGER_ROLES
    entry_type = LedgerEntry.Type.REFUND
