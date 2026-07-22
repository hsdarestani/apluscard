from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from .experience_models import TransactionCase
from .models import AppNotification, LedgerEntry, Location, Membership, Offer, PaymentRequest, PushDevice, Wallet


class LocationSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    short_description = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = ["id", "name", "slug", "address", "image_url", "short_description", "google_review_url", "instagram_url", "tiktok_url", "position"]

    def _visual(self, obj):
        try:
            return obj.visual
        except ObjectDoesNotExist:
            return None

    def get_image_url(self, obj):
        visual = self._visual(obj)
        if not visual or not visual.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(visual.image.url) if request else visual.image.url

    def get_short_description(self, obj):
        visual = self._visual(obj)
        return visual.short_description if visual else ""


class LedgerEntrySerializer(serializers.ModelSerializer):
    performed_by = serializers.CharField(source="performed_by.username", read_only=True)
    location = LocationSerializer(read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ["id", "bill_number", "entry_type", "amount", "balance_before", "balance_after", "description", "order_reference", "performed_by", "location", "payment_request_id", "created_at"]


class WalletSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source="business.currency", read_only=True)
    business = serializers.CharField(source="business.name", read_only=True)
    tier_label = serializers.CharField(source="get_tier_display", read_only=True)
    email_verified = serializers.SerializerMethodField()
    birth_date = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ["id", "member_number", "display_name", "status", "tier", "tier_label", "monthly_topup_total", "balance", "currency", "business", "qr_token", "email_verified", "birth_date", "updated_at"]

    def get_email_verified(self, obj):
        profile = getattr(obj.owner, "member_profile", None) if obj.owner else None
        return bool(profile and profile.email_verified)

    def get_birth_date(self, obj):
        profile = getattr(obj.owner, "member_profile", None) if obj.owner else None
        return profile.birth_date if profile else None


class OfferSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = ["id", "location", "title", "body", "image_url", "target_tier", "starts_at", "ends_at", "created_at"]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class PaymentRequestSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    member_number = serializers.CharField(source="wallet.member_number", read_only=True)
    member_name = serializers.CharField(source="wallet.display_name", read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PaymentRequest
        fields = ["id", "location", "member_number", "member_name", "base_amount", "tip_percentage", "tip_amount", "total_amount", "tip_recipient", "tip_employee_id", "description", "order_reference", "customer_confirmation_required", "status", "created_at", "expires_at", "confirmed_at", "purchase_entry_id", "tip_entry_id"]


class MoneyActionSerializer(serializers.Serializer):
    wallet_token = serializers.UUIDField()
    location_id = serializers.UUIDField(required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    tip_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00"), required=False, default=Decimal("0.00"))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    order_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class PaymentConfirmSerializer(serializers.Serializer):
    tip_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00"))


class AppNotificationSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = AppNotification
        fields = ["id", "kind", "title", "body", "data", "location_name", "is_read", "created_at"]


class TransactionCaseSerializer(serializers.ModelSerializer):
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    member_number = serializers.CharField(source="wallet.member_number", read_only=True)
    member_name = serializers.CharField(source="wallet.display_name", read_only=True)
    bill_number = serializers.CharField(source="ledger_entry.bill_number", read_only=True)
    original_amount = serializers.DecimalField(source="ledger_entry.amount", max_digits=12, decimal_places=2, read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    opened_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TransactionCase
        fields = [
            "id", "case_number", "reason", "reason_label", "status", "status_label",
            "member_number", "member_name", "ledger_entry_id", "bill_number", "original_amount",
            "location_name", "description", "requested_amount", "approved_amount", "manager_note",
            "opened_by_role", "opened_by_name", "reviewed_by_name", "refund_entry_id",
            "created_at", "reviewed_at", "updated_at",
        ]

    def get_opened_by_name(self, obj):
        return obj.opened_by.get_full_name() or obj.opened_by.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username


class TransactionCaseCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=TransactionCase.Reason.choices)
    description = serializers.CharField(min_length=8, max_length=2000)
    requested_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False, allow_null=True)


class TransactionCaseReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[
        TransactionCase.Status.IN_REVIEW,
        TransactionCase.Status.APPROVED,
        TransactionCase.Status.REJECTED,
    ])
    approved_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False, allow_null=True)
    manager_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class PushDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushDevice
        fields = ["platform", "token"]

    def create(self, validated_data):
        device, _ = PushDevice.objects.update_or_create(token=validated_data["token"], defaults={"user": self.context["request"].user, "platform": validated_data["platform"], "is_active": True})
        return device


class MeSerializer(serializers.Serializer):
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    email_verified = serializers.BooleanField()
    roles = serializers.ListField(child=serializers.DictField())
    customer_wallets = WalletSerializer(many=True)

    @staticmethod
    def from_user(user):
        memberships = Membership.objects.select_related("business").filter(user=user, is_active=True)
        profile = getattr(user, "member_profile", None)
        return {"username": user.username, "first_name": user.first_name, "last_name": user.last_name, "email": user.email, "email_verified": bool(profile and profile.email_verified), "roles": [{"business": item.business.name, "business_slug": item.business.slug, "role": item.role, "can_manage_content": item.can_manage_content} for item in memberships], "customer_wallets": Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(owner=user)}
