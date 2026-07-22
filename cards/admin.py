from django.contrib import admin

from .experience_models import LocationVisual, MemberNumberSequence, TransactionCase
from .legal_models import AccountDeletionRequest, LegalAcceptance, LegalConfiguration, PrivacyPreference
from .models import AppNotification, AuditEvent, Business, BusinessSettings, LedgerEntry, Location, MemberProfile, Membership, Offer, PaymentRequest, PushDevice, ReviewStatus, Wallet


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "currency", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "position", "is_active")
    list_filter = ("business", "is_active")
    search_fields = ("name", "address")


@admin.register(LocationVisual)
class LocationVisualAdmin(admin.ModelAdmin):
    list_display = ("location", "short_description", "updated_at")
    search_fields = ("location__name", "short_description")


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    list_display = ("business", "require_customer_confirmation", "tip_allocation", "gold_threshold", "platinum_threshold", "official_invoice_enabled")


@admin.register(MemberNumberSequence)
class MemberNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("next_number", "updated_at")
    readonly_fields = ("id", "updated_at")
    def has_add_permission(self, request): return not MemberNumberSequence.objects.exists()
    def has_delete_permission(self, request, obj=None): return False


@admin.register(LegalConfiguration)
class LegalConfigurationAdmin(admin.ModelAdmin):
    list_display = ("business", "app_display_name", "terms_version", "privacy_version", "is_published", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("business__name", "app_display_name", "controller_name", "contact_email", "privacy_email")


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(admin.ModelAdmin):
    list_display = ("accepted_at", "business", "user", "document_type", "version", "source", "member_number")
    list_filter = ("business", "document_type", "version", "source")
    search_fields = ("user__username", "user__email", "member_number", "email_hash")
    readonly_fields = [field.name for field in LegalAcceptance._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(PrivacyPreference)
class PrivacyPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "marketing_push_enabled", "marketing_email_enabled", "consented_at", "withdrawn_at", "updated_at")
    list_filter = ("business", "marketing_push_enabled", "marketing_email_enabled")
    search_fields = ("user__username", "user__email")


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ("requested_at", "reference_number", "business", "email", "member_number", "status", "completed_at")
    list_filter = ("business", "status", "requested_at")
    search_fields = ("reference_number", "email", "member_number")
    readonly_fields = ("id", "reference_number", "requested_ip", "requested_user_agent", "requested_at")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role", "can_manage_content", "is_active")
    list_filter = ("role", "can_manage_content", "is_active", "business")
    search_fields = ("user__username", "user__email", "business__name")


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "birth_date", "age_confirmed", "email_verified", "email_verified_at")
    list_filter = ("age_confirmed", "email_verified")
    search_fields = ("user__username", "user__email")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("member_number", "display_name", "business", "tier", "monthly_topup_total", "balance", "status", "updated_at")
    list_filter = ("tier", "status", "business")
    search_fields = ("member_number", "display_name", "phone", "email", "qr_token")
    readonly_fields = ("id", "member_number", "qr_token", "balance", "created_at", "updated_at")


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "wallet", "location", "base_amount", "tip_amount", "status", "created_by")
    list_filter = ("status", "business", "location", "tip_recipient")
    search_fields = ("wallet__member_number", "wallet__display_name", "order_reference")
    readonly_fields = [field.name for field in PaymentRequest._meta.fields]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "bill_number", "wallet", "location", "entry_type", "amount", "balance_after", "performed_by")
    list_filter = ("entry_type", "business", "location", "created_at")
    search_fields = ("bill_number", "wallet__member_number", "wallet__display_name", "order_reference", "description", "idempotency_key")
    readonly_fields = [field.name for field in LedgerEntry._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(TransactionCase)
class TransactionCaseAdmin(admin.ModelAdmin):
    list_display = ("created_at", "case_number", "business", "wallet", "reason", "status", "requested_amount", "approved_amount", "reviewed_by")
    list_filter = ("business", "location", "reason", "status", "opened_by_role")
    search_fields = ("case_number", "wallet__member_number", "wallet__display_name", "ledger_entry__bill_number", "description", "manager_note")
    readonly_fields = ("id", "case_number", "business", "location", "wallet", "ledger_entry", "opened_by", "opened_by_role", "created_at", "updated_at", "refund_entry")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("title", "business", "location", "target_tier", "is_active", "created_at")
    list_filter = ("business", "location", "target_tier", "is_active")
    search_fields = ("title", "body")


@admin.register(ReviewStatus)
class ReviewStatusAdmin(admin.ModelAdmin):
    list_display = ("wallet", "location", "completed_at")
    list_filter = ("location",)


@admin.register(AppNotification)
class AppNotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "kind", "location", "is_read")
    list_filter = ("kind", "is_read", "business", "location")
    search_fields = ("recipient__username", "title", "body")


@admin.register(PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__username", "token")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "business", "actor", "action", "object_type", "object_id")
    list_filter = ("business", "action", "created_at")
    search_fields = ("actor__username", "object_id", "action")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
