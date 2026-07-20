from django.contrib import admin

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


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    list_display = ("business", "require_customer_confirmation", "tip_allocation", "gold_threshold", "platinum_threshold", "official_invoice_enabled")


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
