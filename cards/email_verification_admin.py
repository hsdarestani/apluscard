from django.contrib import admin

from .email_verification_models import EmailVerificationAttempt


@admin.register(EmailVerificationAttempt)
class EmailVerificationAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "email",
        "trigger",
        "status",
        "accepted_at",
        "clicked_at",
        "confirmed_at",
        "click_count",
        "error_class",
    )
    list_filter = ("status", "trigger", "created_at")
    search_fields = ("email", "user__username", "user__email", "token_hash", "error_class", "error_detail")
    readonly_fields = [field.name for field in EmailVerificationAttempt._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
