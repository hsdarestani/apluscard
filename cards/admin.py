from django.contrib import admin

from .models import AuditEvent, Business, LedgerEntry, Membership, Wallet


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "currency", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role", "is_active")
    list_filter = ("role", "is_active", "business")
    search_fields = ("user__username", "user__email", "business__name")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("display_name", "business", "balance", "status", "phone", "updated_at")
    list_filter = ("status", "business")
    search_fields = ("display_name", "phone", "email", "qr_token")
    readonly_fields = ("id", "qr_token", "balance", "created_at", "updated_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "wallet", "entry_type", "amount", "balance_after", "performed_by", "order_reference")
    list_filter = ("entry_type", "business", "created_at")
    search_fields = ("wallet__display_name", "order_reference", "description", "idempotency_key")
    readonly_fields = [field.name for field in LedgerEntry._meta.fields]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "business", "actor", "action", "object_type", "object_id")
    list_filter = ("business", "action", "created_at")
    search_fields = ("actor__username", "object_id", "action")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
