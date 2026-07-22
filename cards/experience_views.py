from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .experience_forms import TransactionCaseForm, TransactionCaseReviewForm
from .experience_models import TransactionCase
from .experience_services import create_transaction_case, review_transaction_case
from .models import AppNotification, LedgerEntry, Membership, Wallet
from .services import MANAGER_ROLES, STAFF_ROLES, get_active_membership
from .views import client_ip
from .wallet_pass import build_pkpass


def _safe_next(request, default="dashboard"):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(default)


@login_required
def customer_location_select(request):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), owner=request.user)
    locations = wallet.business.locations.filter(is_active=True).select_related("visual")
    if request.method == "POST":
        location = get_object_or_404(locations, pk=request.POST.get("location_id"))
        request.session["active_location_id"] = str(location.pk)
        messages.success(request, f"{location.name} wurde als aktueller Standort ausgewählt.")
        return redirect(_safe_next(request, "customer_dashboard"))
    return render(
        request,
        "cards/customer_location_select.html",
        {
            "wallet": wallet,
            "locations": locations,
            "next_url": _safe_next(request, "customer_dashboard"),
        },
    )


@login_required
def notification_center(request):
    notifications = request.user.app_notifications.select_related("business", "location")[:250]
    return render(
        request,
        "cards/notification_center.html",
        {
            "notifications": notifications,
            "unread_count": notifications.filter(is_read=False).count() if hasattr(notifications, "filter") else 0,
        },
    )


@login_required
@require_POST
def notification_read(request, notification_id):
    notification = get_object_or_404(AppNotification, pk=notification_id, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    target = notification.data.get("url") if isinstance(notification.data, dict) else None
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=False):
        return redirect(target)
    return redirect(_safe_next(request, "notification_center"))


@login_required
@require_POST
def notifications_read_all(request):
    request.user.app_notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, "Alle Mitteilungen wurden als gelesen markiert.")
    return redirect("notification_center")


@login_required
def apple_wallet_pass(request):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), owner=request.user)
    try:
        pass_data = build_pkpass(wallet, request)
    except ImproperlyConfigured as exc:
        messages.error(request, str(exc))
        return redirect("customer_dashboard")
    response = HttpResponse(pass_data, content_type="application/vnd.apple.pkpass")
    response["Content-Disposition"] = f'attachment; filename="SAMS-Mitglied-{wallet.member_number}.pkpass"'
    response["Cache-Control"] = "private, no-store"
    return response


def _case_access(user, transaction_case):
    if transaction_case.wallet.owner_id == user.id:
        return "customer"
    membership = get_active_membership(user, transaction_case.business)
    if membership and membership.role in MANAGER_ROLES:
        return "manager"
    if membership and membership.role in STAFF_ROLES and (
        transaction_case.opened_by_id == user.id
        or transaction_case.ledger_entry.performed_by_id == user.id
    ):
        return "staff"
    raise PermissionDenied


@login_required
def transaction_case_create(request, entry_id):
    entry = get_object_or_404(
        LedgerEntry.objects.select_related("business", "location", "wallet", "wallet__owner", "performed_by"),
        pk=entry_id,
    )
    # Permission is checked before rendering and again atomically by the service.
    if entry.wallet.owner_id != request.user.id:
        membership = get_active_membership(request.user, entry.business)
        if not membership or membership.role not in STAFF_ROLES or entry.performed_by_id != request.user.id:
            raise PermissionDenied

    form = TransactionCaseForm(request.POST or None, ledger_entry=entry)
    if request.method == "POST" and form.is_valid():
        try:
            transaction_case = create_transaction_case(
                entry=entry,
                opened_by=request.user,
                reason=form.cleaned_data["reason"],
                description=form.cleaned_data["description"],
                requested_amount=form.cleaned_data.get("requested_amount"),
                ip_address=client_ip(request),
            )
        except (ValidationError, PermissionDenied) as exc:
            detail = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, detail)
        else:
            messages.success(request, f"Fall {transaction_case.case_number} wurde eingereicht.")
            return redirect("transaction_case_detail", case_id=transaction_case.pk)
    return render(request, "cards/transaction_case_form.html", {"entry": entry, "form": form})


@login_required
def transaction_case_detail(request, case_id):
    transaction_case = get_object_or_404(
        TransactionCase.objects.select_related(
            "business",
            "location",
            "wallet",
            "wallet__owner",
            "ledger_entry",
            "ledger_entry__performed_by",
            "opened_by",
            "reviewed_by",
            "refund_entry",
        ),
        pk=case_id,
    )
    access = _case_access(request.user, transaction_case)
    membership = get_active_membership(request.user, transaction_case.business)
    review_form = TransactionCaseReviewForm(transaction_case=transaction_case)
    return render(
        request,
        "cards/transaction_case_detail.html",
        {
            "case": transaction_case,
            "access": access,
            "membership": membership,
            "review_form": review_form,
            "can_approve": bool(membership and membership.role == Membership.Role.OWNER),
        },
    )


@login_required
def transaction_cases(request):
    membership = get_active_membership(request.user)
    wallet = Wallet.objects.filter(owner=request.user).first()
    if membership and membership.role in MANAGER_ROLES:
        cases = TransactionCase.objects.filter(business=membership.business)
        title = "Transaktionsfälle der Verwaltung"
    elif membership and membership.role in STAFF_ROLES:
        cases = TransactionCase.objects.filter(business=membership.business).filter(
            opened_by=request.user
        )
        title = "Meine Korrekturanfragen"
    elif wallet:
        cases = TransactionCase.objects.filter(wallet=wallet)
        title = "Meine Transaktionsfälle"
    else:
        raise PermissionDenied
    cases = cases.select_related("wallet", "ledger_entry", "location", "opened_by", "reviewed_by")[:250]
    return render(request, "cards/transaction_case_list.html", {"cases": cases, "title": title})


@login_required
@require_POST
def transaction_case_review(request, case_id):
    transaction_case = get_object_or_404(TransactionCase.objects.select_related("business", "ledger_entry"), pk=case_id)
    membership = get_active_membership(request.user, transaction_case.business)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    form = TransactionCaseReviewForm(request.POST, transaction_case=transaction_case)
    if form.is_valid():
        try:
            review_transaction_case(
                transaction_case=transaction_case,
                reviewer=request.user,
                action=form.cleaned_data["action"],
                manager_note=form.cleaned_data.get("manager_note", ""),
                approved_amount=form.cleaned_data.get("approved_amount"),
                ip_address=client_ip(request),
            )
        except (ValidationError, PermissionDenied) as exc:
            detail = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, detail)
        else:
            messages.success(request, "Der Transaktionsfall wurde aktualisiert.")
    else:
        messages.error(request, "Bitte die markierten Angaben prüfen.")
    return redirect("transaction_case_detail", case_id=transaction_case.pk)
