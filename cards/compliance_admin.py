from django.contrib import admin

from .compliance_models import TestWalletMarker


@admin.register(TestWalletMarker)
class TestWalletMarkerAdmin(admin.ModelAdmin):
    list_display = ("wallet", "reason", "marked_by", "created_at")
    search_fields = ("wallet__member_number", "wallet__display_name", "reason")
    readonly_fields = ("created_at",)

    def save_model(self, request, obj, form, change):
        if obj.marked_by_id is None:
            obj.marked_by = request.user
        super().save_model(request, obj, form, change)
