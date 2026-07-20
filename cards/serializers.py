from decimal import Decimal

from rest_framework import serializers

from .models import LedgerEntry, Membership, Wallet


class LedgerEntrySerializer(serializers.ModelSerializer):
    performed_by = serializers.CharField(source="performed_by.username", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ["id", "entry_type", "amount", "balance_before", "balance_after", "description", "order_reference", "performed_by", "created_at"]


class WalletSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source="business.currency", read_only=True)
    business = serializers.CharField(source="business.name", read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "display_name", "status", "balance", "currency", "business", "qr_token", "updated_at"]


class MoneyActionSerializer(serializers.Serializer):
    wallet_token = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    order_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class MeSerializer(serializers.Serializer):
    username = serializers.CharField()
    roles = serializers.ListField(child=serializers.DictField())
    customer_wallets = WalletSerializer(many=True)

    @staticmethod
    def from_user(user):
        memberships = Membership.objects.select_related("business").filter(user=user, is_active=True)
        return {
            "username": user.username,
            "roles": [{"business": item.business.name, "business_slug": item.business.slug, "role": item.role} for item in memberships],
            "customer_wallets": Wallet.objects.select_related("business").filter(owner=user),
        }
