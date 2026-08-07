from django.contrib import admin

from .security_models import AuditChainSeal, PrivilegedMfaDevice


@admin.register(PrivilegedMfaDevice)
class PrivilegedMfaDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "is_confirmed", "confirmed_at", "updated_at")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    readonly_fields = (
        "user",
        "secret_encrypted",
        "is_confirmed",
        "confirmed_at",
        "last_counter",
        "recovery_code_hashes",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Emergency reset must be performed with the dedicated management command
        # so it is auditable and cannot happen accidentally in Admin.
        return False


@admin.register(AuditChainSeal)
class AuditChainSealAdmin(admin.ModelAdmin):
    list_display = ("business", "sequence", "audit_event", "event_hash", "created_at")
    list_filter = ("business",)
    search_fields = ("event_hash", "previous_hash", "audit_event__action", "audit_event__object_id")
    readonly_fields = (
        "audit_event",
        "business",
        "sequence",
        "previous_hash",
        "event_hash",
        "created_at",
    )
    ordering = ("business", "sequence")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
