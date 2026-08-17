from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .email_verification_models import EmailVerificationAttempt
from .emailing import send_verification_email
from .experience_models import LocationVisual, MemberNumberSequence, TransactionCase
from .legal_models import AccountDeletionRequest, LegalAcceptance, LegalConfiguration, PrivacyPreference
from .models import AppNotification, AuditEvent, Business, BusinessSettings, LedgerEntry, Location, MemberProfile, Membership, Offer, PaymentRequest, PushDevice, ReviewStatus, Wallet
from .push_models import PushDelivery
from .test_data_cleanup import build_test_data_preview, purge_test_data


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
    list_display = ("user", "birth_date", "age_confirmed", "email_verified", "email_verified_at", "resend_verification_button")
    list_filter = ("age_confirmed", "email_verified")
    search_fields = ("user__username", "user__email")
    actions = ("resend_verification_selected",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:profile_id>/resend-verification/",
                self.admin_site.admin_view(self.resend_verification_view),
                name="cards_memberprofile_resend_verification",
            )
        ]
        return custom + urls

    @admin.display(description="E-Mail-Bestätigung")
    def resend_verification_button(self, obj):
        if obj.email_verified:
            return "Bestätigt"
        if not (obj.user.email or "").strip():
            return "Keine E-Mail"
        url = reverse("admin:cards_memberprofile_resend_verification", args=[obj.pk])
        return format_html('<a class="button" href="{}">Erneut senden</a>', url)

    @admin.action(description="Bestätigungs-E-Mail erneut senden")
    def resend_verification_selected(self, request, queryset):
        sent_count = 0
        failed_count = 0
        skipped_count = 0
        for profile in queryset.select_related("user"):
            email = (profile.user.email or "").strip()
            if profile.email_verified or not email:
                skipped_count += 1
                continue
            try:
                send_verification_email(
                    request,
                    profile.user,
                    trigger=EmailVerificationAttempt.Trigger.RESEND,
                )
            except Exception:
                failed_count += 1
            else:
                sent_count += 1

        if sent_count:
            self.message_user(
                request,
                f"{sent_count} Bestätigungs-E-Mail(s) wurden erneut versendet.",
                level=messages.SUCCESS,
            )
        if failed_count:
            self.message_user(
                request,
                f"{failed_count} Versandversuch(e) sind fehlgeschlagen. Details stehen unter E-Mail-Bestätigungsversuche.",
                level=messages.ERROR,
            )
        if skipped_count:
            self.message_user(
                request,
                f"{skipped_count} Profil(e) wurden übersprungen, weil sie bereits bestätigt sind oder keine E-Mail-Adresse haben.",
                level=messages.WARNING,
            )

    def resend_verification_view(self, request, profile_id):
        profile = get_object_or_404(MemberProfile.objects.select_related("user"), pk=profile_id)
        if not self.has_change_permission(request, profile):
            raise PermissionDenied

        email = (profile.user.email or "").strip()
        if request.method == "POST":
            if profile.email_verified:
                messages.info(request, "Diese E-Mail-Adresse ist bereits bestätigt.")
            elif not email:
                messages.error(request, "Für dieses Mitglied ist keine E-Mail-Adresse hinterlegt.")
            else:
                try:
                    send_verification_email(
                        request,
                        profile.user,
                        trigger=EmailVerificationAttempt.Trigger.RESEND,
                    )
                except Exception:
                    messages.error(
                        request,
                        "Die Bestätigungs-E-Mail konnte nicht versendet werden. Details stehen unter E-Mail-Bestätigungsversuche.",
                    )
                else:
                    messages.success(request, f"Bestätigungs-E-Mail wurde erneut an {email} gesendet.")
            return redirect(reverse("admin:cards_memberprofile_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Bestätigungs-E-Mail erneut senden",
            "opts": self.model._meta,
            "profile": profile,
            "email": email,
            "changelist_url": reverse("admin:cards_memberprofile_changelist"),
        }
        return TemplateResponse(
            request,
            "admin/cards/memberprofile/resend_verification.html",
            context,
        )


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("member_number", "display_name", "business", "tier", "monthly_topup_total", "balance", "status", "updated_at")
    list_filter = ("tier", "status", "business")
    search_fields = ("member_number", "display_name", "phone", "email", "qr_token")
    readonly_fields = ("id", "member_number", "qr_token", "balance", "created_at", "updated_at")
    change_list_template = "admin/cards/wallet/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "testdaten-bereinigen/",
                self.admin_site.admin_view(self.test_data_cleanup_view),
                name="cards_wallet_test_data_cleanup",
            )
        ]
        return custom + urls

    def test_data_cleanup_view(self, request):
        if not request.user.is_active or not request.user.is_superuser:
            raise PermissionDenied

        preview = build_test_data_preview()
        if request.method == "POST":
            if not settings.ALLOW_TEST_DATA_PURGE:
                messages.error(
                    request,
                    "Testdaten-Löschung ist in Production gesperrt. ALLOW_TEST_DATA_PURGE muss zuerst bewusst aktiviert werden.",
                )
            elif request.POST.get("confirmation", "").strip() != "TESTDATEN LÖSCHEN":
                messages.error(request, "Bestätigung stimmt nicht. Es wurde nichts gelöscht.")
            else:
                before_total = preview["total_records"]
                before_blocked = preview["blocked_user_count"]
                purge_test_data()
                messages.success(
                    request,
                    f"Testdaten-Bereinigung abgeschlossen. Vorher erkannt: {before_total} Datensätze. "
                    f"Aus Sicherheitsgründen blockierte Benutzer: {before_blocked}.",
                )
                return redirect(reverse("admin:cards_wallet_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Testdaten sicher bereinigen",
            "opts": self.model._meta,
            "preview": preview,
            "purge_enabled": settings.ALLOW_TEST_DATA_PURGE,
            "changelist_url": reverse("admin:cards_wallet_changelist"),
        }
        return TemplateResponse(request, "admin/cards/wallet/test_data_cleanup.html", context)


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
    list_display = ("created_at", "recipient", "kind", "title", "location", "is_read")
    list_filter = ("kind", "is_read", "business", "location")
    search_fields = ("recipient__username", "title", "body")


@admin.register(PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__username", "token")


@admin.register(PushDelivery)
class PushDeliveryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "notification", "status", "attempts", "sent_count", "processed_at")
    list_filter = ("status", "created_at")
    search_fields = ("notification__recipient__username", "notification__title", "last_error")
    readonly_fields = [field.name for field in PushDelivery._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "business", "actor", "action", "object_type", "object_id")
    list_filter = ("business", "action", "created_at")
    search_fields = ("actor__username", "object_id", "action")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
