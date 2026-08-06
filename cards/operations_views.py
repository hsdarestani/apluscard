import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .experience_models import TransactionCase
from . import experience_services
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

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _extract_wallet_token(value):
    match = UUID_PATTERN.search(str(value or "").strip())
    return match.group(0) if match else None


def _form_error_text(form):
    parts = []
    for field_name, errors in form.errors.items():
        label = form.fields.get(field_name).label if field_name in form.fields else "Formular"
        for error in errors:
            parts.append(f"{label}: {error}")
    return " ".join(parts)


def _notification_data(request):
    target_url = request.POST.get("target_url", "").strip()
    if target_url and not target_url.startswith("/"):
        target_url = ""
    data = {"url": target_url or "/mitteilungen/"}
    return data


@login_required
@require_POST
def staff_charge_safe(request):
    """Staff payment endpoint that never exposes a raw 404 for scan/input errors."""
    from .forms import MoneyActionForm

    membership = get_active_membership(request.user)
    if not membership or membership.role not in STAFF_ROLES:
        raise PermissionDenied

    token = _extract_wallet_token(request.POST.get("wallet_token"))
    if token is None:
        messages.error(request, "Der QR-Code enthält keinen gültigen Mitgliedscode. Bitte erneut scannen oder den Code manuell eingeben.")
        return redirect("staff_dashboard")

    normalized_data = request.POST.copy()
    normalized_data["wallet_token"] = token
    form = MoneyActionForm(normalized_data)
    if not form.is_valid():
        messages.error(request, _form_error_text(form) or "Bitte Kartencode, Betrag, Standort und Trinkgeld prüfen.")
        return redirect("staff_dashboard")

    wallet = Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(
        business=membership.business,
        qr_token=token,
    ).first()
    if wallet is None:
        messages.error(request, "Diese Mitgliedskarte wurde nicht gefunden oder gehört zu einem anderen Betrieb.")
        return redirect("staff_dashboard")

    location_id = form.cleaned_data.get("location_id") or request.session.get("active_location_id")
    location = Location.objects.filter(
        pk=location_id,
        business=membership.business,
        is_active=True,
    ).first()
    if location is None:
        messages.error(request, "Der ausgewählte Standort ist nicht mehr verfügbar. Bitte Standort erneut auswählen.")
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
            messages.success(request, f"Zahlungsfreigabe wurde an Mitglied {wallet.member_number} gesendet.")
        else:
            messages.success(request, f"{payment.base_amount:.2f} € Zahlung + {payment.tip_amount:.2f} € Trinkgeld wurden abgebucht.")
    return redirect("staff_dashboard")


def _management_membership(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    return membership


def _can_manage_content(membership):
    return membership.role in OWNER_ROLES or membership.can_manage_content


@login_required
@require_POST
def manager_broadcast_notification(request):
    membership = _management_membership(request)
    if not _can_manage_content(membership):
        raise PermissionDenied

    title = request.POST.get("title", "").strip()[:160]
    body = request.POST.get("body", "").strip()
    target = request.POST.get("target", "ALL").strip().upper()
    kind = request.POST.get("kind", AppNotification.Kind.SYSTEM).strip().upper()
    if kind not in AppNotification.Kind.values:
        kind = AppNotification.Kind.SYSTEM
    if not title or not body:
        messages.error(request, "Titel und Nachricht dürfen nicht leer sein.")
        return redirect("manager_settings")

    wallets = Wallet.objects.filter(
        business=membership.business,
        owner__isnull=False,
        status=Wallet.Status.ACTIVE,
    ).select_related("owner")
    if target in {Wallet.Tier.SILVER, Wallet.Tier.GOLD, Wallet.Tier.PLATINUM}:
        wallets = wallets.filter(tier=target)
    users = [wallet.owner for wallet in wallets]
    created = experience_services.create_notifications(
        users=users,
        business=membership.business,
        title=title,
        body=body,
        kind=kind,
        data=_notification_data(request),
    )
    messages.success(request, f"Die Mitteilung wurde für {len(created)} Mitglieder angelegt und für Push eingeplant.")
    return redirect("manager_settings")


@login_required
@require_POST
def manager_direct_notification(request, wallet_id):
    membership = _management_membership(request)
    wallet = Wallet.objects.select_related("owner").filter(pk=wallet_id, business=membership.business).first()
    if wallet is None:
        messages.error(request, "Mitgliedskarte wurde nicht gefunden.")
        return redirect("manager_dashboard")
    if wallet.owner is None:
        messages.error(request, "Für diese Karte ist noch kein Benutzerkonto verbunden.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    title = request.POST.get("title", "").strip()[:160]
    body = request.POST.get("body", "").strip()
    kind = request.POST.get("kind", AppNotification.Kind.SYSTEM).strip().upper()
    if kind not in AppNotification.Kind.values:
        kind = AppNotification.Kind.SYSTEM
    if not title or not body:
        messages.error(request, "Titel und Nachricht dürfen nicht leer sein.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    experience_services.create_notifications(
        users=[wallet.owner],
        business=membership.business,
        title=title,
        body=body,
        kind=kind,
        data=_notification_data(request),
    )
    messages.success(request, f"Mitteilung an {wallet.display_name} wurde angelegt und für Push eingeplant.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


def _delete_wallet_transactions(wallet):
    transaction_cases = TransactionCase.objects.filter(wallet=wallet)
    case_ids = [str(value) for value in transaction_cases.values_list("pk", flat=True)]
    transaction_cases.delete()

    payments = PaymentRequest.objects.filter(wallet=wallet)
    payment_ids = [str(value) for value in payments.values_list("pk", flat=True)]
    payments.delete()

    entries = LedgerEntry.objects.filter(wallet=wallet)
    entry_ids = [str(value) for value in entries.values_list("pk", flat=True)]
    entries.delete()

    if wallet.owner_id:
        AppNotification.objects.filter(recipient_id=wallet.owner_id, kind=AppNotification.Kind.PAYMENT).delete()
    AuditEvent.objects.filter(
        business=wallet.business,
        object_id__in=case_ids + payment_ids + entry_ids,
    ).delete()
    Wallet.objects.filter(pk=wallet.pk).update(
        balance=Decimal("0.00"),
        monthly_topup_total=Decimal("0.00"),
        tier=Wallet.Tier.SILVER,
    )


@login_required
@require_POST
def manager_clear_wallet_history(request, wallet_id):
    membership = _management_membership(request)
    require_role(request.user, membership.business, OWNER_ROLES)
    wallet = Wallet.objects.filter(pk=wallet_id, business=membership.business).first()
    if wallet is None:
        messages.error(request, "Mitgliedskarte wurde nicht gefunden.")
        return redirect("manager_dashboard")
    if request.POST.get("confirmation", "").strip().upper() != "LÖSCHEN":
        messages.error(request, "Zum Löschen bitte LÖSCHEN in das Bestätigungsfeld eingeben.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    with transaction.atomic():
        _delete_wallet_transactions(wallet)
    messages.success(request, f"Die Test-Transaktionshistorie von {wallet.display_name} wurde gelöscht und der Saldo auf 0,00 € gesetzt.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
@require_POST
def manager_delete_test_account(request, wallet_id):
    membership = _management_membership(request)
    require_role(request.user, membership.business, OWNER_ROLES)
    wallet = Wallet.objects.select_related("owner").filter(pk=wallet_id, business=membership.business).first()
    if wallet is None:
        messages.error(request, "Mitgliedskarte wurde nicht gefunden.")
        return redirect("manager_dashboard")
    if request.POST.get("confirmation", "").strip().upper() != "TESTKONTO LÖSCHEN":
        messages.error(request, "Zum Löschen bitte TESTKONTO LÖSCHEN vollständig eingeben.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    user = wallet.owner
    label = wallet.display_name
    with transaction.atomic():
        _delete_wallet_transactions(wallet)
        ReviewStatus.objects.filter(wallet=wallet).delete()
        if user is not None:
            AppNotification.objects.filter(recipient=user).delete()
            PushDevice.objects.filter(user=user).delete()
        wallet.delete()
        if user is not None and not user.is_superuser and not user.business_memberships.filter(is_active=True).exists():
            user.delete()
    messages.success(request, f"Testkonto {label} und die zugehörigen Testdaten wurden vollständig gelöscht.")
    return redirect("manager_dashboard")


@login_required
def privacy_choices_safe(request):
    """Only customer accounts have privacy marketing preferences; management is redirected safely."""
    if not Wallet.objects.filter(owner=request.user).exists():
        messages.info(request, "Datenschutz-Einstellungen für Marketing sind nur für Mitgliedskonten verfügbar.")
        return redirect("dashboard")
    from .legal_views import privacy_choices

    return privacy_choices(request)
