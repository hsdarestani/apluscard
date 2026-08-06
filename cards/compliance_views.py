import json
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import experience_services
from .compliance_models import TestWalletMarker
from .compliance_qr import resolve_identity_qr, resolve_payment_qr, wallet_qr_payload
from .experience_models import TransactionCase
from .legal_models import AccountDeletionRequest, LegalAcceptance, PrivacyPreference
from .models import (
    AppNotification,
    AuditEvent,
    LedgerEntry,
    Location,
    Membership,
    PaymentRequest,
    PushDevice,
    ReviewStatus,
    Wallet,
)
from .services import MANAGER_ROLES, OWNER_ROLES, STAFF_ROLES, create_payment_request, get_active_membership, require_role


class SecureMoneyActionForm(forms.Form):
    wallet_token = forms.CharField(label="Sicherer Kartencode", max_length=1200)
    location_id = forms.UUIDField(label="Standort")
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    tip_amount = forms.DecimalField(
        label="Trinkgeld in Euro",
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        max_digits=8,
        decimal_places=2,
        required=False,
    )
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Bestellnummer", max_length=100, required=False)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _form_error_text(form):
    parts = []
    for field_name, errors in form.errors.items():
        label = form.fields.get(field_name).label if field_name in form.fields else "Formular"
        parts.extend(f"{label}: {error}" for error in errors)
    return " ".join(parts)


def _management_membership(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    return membership


def _test_purge_authorized(wallet):
    return bool(
        settings.ALLOW_TEST_DATA_PURGE
        and TestWalletMarker.objects.filter(wallet=wallet).exists()
    )


@login_required
@require_GET
def customer_qr_refresh(request):
    wallet = Wallet.objects.filter(owner=request.user, status=Wallet.Status.ACTIVE).first()
    if wallet is None:
        raise PermissionDenied
    response = JsonResponse(wallet_qr_payload(wallet))
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


@login_required
@require_POST
def staff_charge_secure(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in STAFF_ROLES:
        raise PermissionDenied

    form = SecureMoneyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_error_text(form) or "Bitte Kartencode, Betrag, Standort und Trinkgeld prüfen.")
        return redirect("staff_dashboard")

    try:
        wallet = resolve_payment_qr(
            form.cleaned_data["wallet_token"],
            business=membership.business,
        )
    except signing.BadSignature:
        messages.error(
            request,
            "Dieser Zahlungs-QR-Code ist ungültig oder abgelaufen. Bitte den aktuellen QR-Code erneut scannen.",
        )
        return redirect("staff_dashboard")

    location = Location.objects.filter(
        pk=form.cleaned_data["location_id"],
        business=membership.business,
        is_active=True,
    ).first()
    if location is None:
        messages.error(request, "Der ausgewählte Standort ist nicht verfügbar.")
        return redirect("staff_dashboard")

    try:
        payment = create_payment_request(
            wallet=wallet,
            location=location,
            actor=request.user,
            amount=form.cleaned_data["amount"],
            tip_amount=form.cleaned_data.get("tip_amount") or Decimal("0.00"),
            description=form.cleaned_data.get("description", ""),
            order_reference=form.cleaned_data.get("order_reference", ""),
            ip_address=_client_ip(request),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if payment.status == PaymentRequest.Status.PENDING:
            messages.success(request, "Die Zahlungsfreigabe wurde an das Kundengerät gesendet.")
        else:
            messages.success(request, f"{payment.base_amount:.2f} € Zahlung + {payment.tip_amount:.2f} € Trinkgeld wurden abgebucht.")
    return redirect("staff_dashboard")


@login_required
@require_GET
def manager_wallet_scan_secure(request):
    membership = _management_membership(request)
    wallet = resolve_identity_qr(request.GET.get("token", ""), business=membership.business)
    if wallet is None:
        messages.error(request, "Der QR-Code ist ungültig, abgelaufen oder gehört nicht zu diesem Betrieb.")
        return redirect("manager_dashboard")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
@require_POST
def manager_clear_wallet_history_guarded(request, wallet_id):
    membership = _management_membership(request)
    require_role(request.user, membership.business, OWNER_ROLES)
    wallet = Wallet.objects.filter(pk=wallet_id, business=membership.business).first()
    if wallet is None:
        messages.error(request, "Mitgliedskarte wurde nicht gefunden.")
        return redirect("manager_dashboard")

    if not _test_purge_authorized(wallet):
        AuditEvent.objects.create(
            actor=request.user,
            business=wallet.business,
            action="financial_hard_delete_denied",
            object_type="wallet",
            object_id=str(wallet.pk),
            details={"reason": "production_or_unmarked_wallet"},
            ip_address=_client_ip(request),
        )
        messages.error(
            request,
            "Produktive Finanzdaten dürfen nicht endgültig gelöscht werden. Korrekturen müssen als Storno oder Gegenbuchung erfolgen.",
        )
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    if request.POST.get("confirmation", "").strip().upper() != "LÖSCHEN":
        messages.error(request, "Zum Löschen bitte LÖSCHEN in das Bestätigungsfeld eingeben.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    from .operations_views import _delete_wallet_transactions

    with transaction.atomic():
        _delete_wallet_transactions(wallet)
        AuditEvent.objects.create(
            actor=request.user,
            business=wallet.business,
            action="test_wallet_history_purged",
            object_type="wallet",
            object_id=str(wallet.pk),
            details={"test_marker": True},
            ip_address=_client_ip(request),
        )
    messages.success(request, f"Die ausdrücklich markierten Testdaten von {wallet.display_name} wurden gelöscht.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
@require_POST
def manager_delete_test_account_guarded(request, wallet_id):
    membership = _management_membership(request)
    require_role(request.user, membership.business, OWNER_ROLES)
    wallet = Wallet.objects.select_related("owner").filter(pk=wallet_id, business=membership.business).first()
    if wallet is None:
        messages.error(request, "Mitgliedskarte wurde nicht gefunden.")
        return redirect("manager_dashboard")

    if not _test_purge_authorized(wallet):
        AuditEvent.objects.create(
            actor=request.user,
            business=wallet.business,
            action="test_account_delete_denied",
            object_type="wallet",
            object_id=str(wallet.pk),
            details={"reason": "production_or_unmarked_wallet"},
            ip_address=_client_ip(request),
        )
        messages.error(request, "Dieses Konto ist nicht als Testkonto markiert oder die Testdaten-Löschung ist deaktiviert.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    if request.POST.get("confirmation", "").strip().upper() != "TESTKONTO LÖSCHEN":
        messages.error(request, "Zum Löschen bitte TESTKONTO LÖSCHEN vollständig eingeben.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    from .operations_views import _delete_wallet_transactions

    user = wallet.owner
    label = wallet.display_name
    business = wallet.business
    wallet_pk = str(wallet.pk)
    with transaction.atomic():
        AuditEvent.objects.create(
            actor=request.user,
            business=business,
            action="test_account_purge_started",
            object_type="wallet",
            object_id=wallet_pk,
            details={"test_marker": True},
            ip_address=_client_ip(request),
        )
        _delete_wallet_transactions(wallet)
        ReviewStatus.objects.filter(wallet=wallet).delete()
        if user is not None:
            AppNotification.objects.filter(recipient=user).delete()
            PushDevice.objects.filter(user=user).delete()
        TestWalletMarker.objects.filter(wallet=wallet).delete()
        wallet.delete()
        if user is not None and not user.is_superuser and not user.business_memberships.filter(is_active=True).exists():
            user.delete()
    messages.success(request, f"Das ausdrücklich markierte Testkonto {label} wurde vollständig gelöscht.")
    return redirect("manager_dashboard")


@login_required
@require_GET
def customer_data_export(request):
    wallet = Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(owner=request.user).first()
    if wallet is None or request.user.business_memberships.filter(is_active=True).exists():
        raise PermissionDenied

    profile = getattr(request.user, "member_profile", None)
    export = {
        "exported_at": timezone.now(),
        "controller": wallet.business.name,
        "account": {
            "id": request.user.pk,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "date_joined": request.user.date_joined,
            "last_login": request.user.last_login,
        },
        "profile": {
            "birth_date": profile.birth_date if profile else None,
            "age_confirmed": bool(profile and profile.age_confirmed),
            "email_verified": bool(profile and profile.email_verified),
            "email_verified_at": profile.email_verified_at if profile else None,
        },
        "wallet": {
            "id": wallet.pk,
            "member_number": wallet.member_number,
            "display_name": wallet.display_name,
            "phone": wallet.phone,
            "email": wallet.email,
            "status": wallet.status,
            "tier": wallet.tier,
            "monthly_topup_total": wallet.monthly_topup_total,
            "balance": wallet.balance,
            "created_at": wallet.created_at,
            "updated_at": wallet.updated_at,
        },
        "ledger_entries": list(
            LedgerEntry.objects.filter(wallet=wallet).values(
                "id", "bill_number", "entry_type", "amount", "balance_before", "balance_after",
                "description", "order_reference", "location_id", "payment_request_id", "performed_by_id", "created_at",
            )
        ),
        "payment_requests": list(
            PaymentRequest.objects.filter(wallet=wallet).values(
                "id", "location_id", "base_amount", "tip_selected_amount", "tip_amount", "tip_recipient",
                "description", "order_reference", "status", "created_by_id", "created_at", "confirmed_at", "expires_at",
            )
        ),
        "transaction_cases": list(
            TransactionCase.objects.filter(wallet=wallet).values(
                "id", "case_number", "reason", "status", "description", "requested_amount", "approved_amount",
                "manager_note", "ledger_entry_id", "opened_by_id", "reviewed_by_id", "created_at", "reviewed_at", "updated_at",
            )
        ),
        "privacy_preferences": list(
            PrivacyPreference.objects.filter(user=request.user, business=wallet.business).values(
                "marketing_push_enabled", "marketing_email_enabled", "consented_at", "withdrawn_at", "updated_at",
            )
        ),
        "legal_acceptances": list(
            LegalAcceptance.objects.filter(user=request.user, business=wallet.business).values(
                "document_type", "version", "source", "accepted_at",
            )
        ),
        "account_deletion_requests": list(
            AccountDeletionRequest.objects.filter(user=request.user, business=wallet.business).values(
                "reference_number", "reason", "status", "requested_at", "completed_at",
            )
        ),
        "notifications": list(
            AppNotification.objects.filter(recipient=request.user, business=wallet.business).values(
                "id", "kind", "title", "body", "data", "location_id", "is_read", "created_at",
            )
        ),
        "push_devices": list(
            PushDevice.objects.filter(user=request.user).values("platform", "is_active", "updated_at")
        ),
    }

    AuditEvent.objects.create(
        actor=request.user,
        business=wallet.business,
        action="gdpr_data_export",
        object_type="wallet",
        object_id=str(wallet.pk),
        details={"format": "json"},
        ip_address=_client_ip(request),
    )
    content = json.dumps(export, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="sams-data-export-{wallet.member_number}.json"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response
