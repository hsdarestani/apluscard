from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .experience_forms import LocationVisualForm, TransactionCaseForm, TransactionCaseReviewForm
from .experience_models import TransactionCase
from .experience_services import create_transaction_case, review_transaction_case
from .models import AppNotification, LedgerEntry, Membership, Wallet
from .services import MANAGER_ROLES, OWNER_ROLES, STAFF_ROLES, get_active_membership, require_role


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def service_worker(request):
    content = """
const CACHE = 'sams-card-v12';
const ASSETS = [
  '/static/cards/app.css',
  '/static/cards/app.js',
  '/static/cards/registration.css',
  '/static/cards/ledger.css',
  '/static/cards/sams-platform.css',
  '/static/cards/legal.css',
  '/static/cards/experience.css',
  '/static/cards/ui-fixes.css',
  '/static/cards/push.css',
  '/static/cards/icon.svg',
  '/app-icon-192.png',
  '/app-icon-512.png',
  '/manifest.webmanifest'
];
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const isAsset = url.pathname.startsWith('/static/') || url.pathname.startsWith('/app-icon-') || url.pathname === '/manifest.webmanifest';
  if (!isAsset) return;
  event.respondWith(
    caches.match(event.request).then(cached => {
      const fresh = fetch(event.request).then(response => {
        if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
        return response;
      });
      return cached || fresh;
    })
  );
});
""".strip()
    response = HttpResponse(content, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store"
    return response


def _safe_next(request, default="dashboard"):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
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
    return render(request, "cards/customer_location_select.html", {"wallet": wallet, "locations": locations, "next_url": _safe_next(request, "customer_dashboard")})


@login_required
def notification_center(request):
    notifications_query = request.user.app_notifications.select_related("business", "location")
    unread_count = notifications_query.filter(is_read=False).count()
    notifications = notifications_query[:250]
    return render(request, "cards/notification_center.html", {"notifications": notifications, "unread_count": unread_count})


@login_required
@require_POST
def notification_read(request, notification_id):
    notification = get_object_or_404(AppNotification, pk=notification_id, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    target = notification.data.get("url") if isinstance(notification.data, dict) else None
    if target and target.startswith("/"):
        return redirect(target)
    return redirect(_safe_next(request, "notification_center"))


@login_required
@require_POST
def notifications_read_all(request):
    request.user.app_notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, "Alle Mitteilungen wurden als gelesen markiert.")
    return redirect("notification_center")


@login_required
@require_POST
def location_visual_update(request):
    membership = get_active_membership(request.user)
    if not membership:
        raise PermissionDenied
    require_role(request.user, membership.business, OWNER_ROLES)
    form = LocationVisualForm(request.POST, request.FILES, business=membership.business)
    if form.is_valid():
        visual = form.save()
        messages.success(request, f"Foto und Beschreibung für {visual.location.name} wurden gespeichert.")
    else:
        messages.error(request, "Standortbild konnte nicht gespeichert werden. Bitte Datei und Angaben prüfen.")
    return redirect("manager_settings")


def _case_access(user, transaction_case):
    if transaction_case.wallet.owner_id == user.id:
        return "customer"
    membership = get_active_membership(user, transaction_case.business)
    if membership and membership.role in MANAGER_ROLES:
        return "manager"
    if membership and membership.role in STAFF_ROLES and (transaction_case.opened_by_id == user.id or transaction_case.ledger_entry.performed_by_id == user.id):
        return "staff"
    raise PermissionDenied


@login_required
def transaction_case_create(request, entry_id):
    entry = get_object_or_404(LedgerEntry.objects.select_related("business", "location", "wallet", "wallet__owner", "performed_by"), pk=entry_id)
    if entry.wallet.owner_id != request.user.id:
        membership = get_active_membership(request.user, entry.business)
        if not membership:
            raise PermissionDenied
        if membership.role not in MANAGER_ROLES and not (membership.role in STAFF_ROLES and entry.performed_by_id == request.user.id):
            raise PermissionDenied

    form = TransactionCaseForm(request.POST or None, ledger_entry=entry)
    if request.method == "POST" and form.is_valid():
        try:
            transaction_case = create_transaction_case(entry=entry, opened_by=request.user, reason=form.cleaned_data["reason"], description=form.cleaned_data["description"], requested_amount=form.cleaned_data.get("requested_amount"), ip_address=client_ip(request))
        except (ValidationError, PermissionDenied) as exc:
            detail = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, detail)
        else:
            messages.success(request, f"Fall {transaction_case.case_number} wurde eingereicht.")
            return redirect("transaction_case_detail", case_id=transaction_case.pk)
    return render(request, "cards/transaction_case_form.html", {"entry": entry, "form": form})


@login_required
def transaction_case_detail(request, case_id):
    transaction_case = get_object_or_404(TransactionCase.objects.select_related("business", "location", "wallet", "wallet__owner", "ledger_entry", "ledger_entry__performed_by", "opened_by", "reviewed_by", "refund_entry"), pk=case_id)
    access = _case_access(request.user, transaction_case)
    membership = get_active_membership(request.user, transaction_case.business)
    review_form = TransactionCaseReviewForm(transaction_case=transaction_case)
    return render(request, "cards/transaction_case_detail.html", {"case": transaction_case, "access": access, "membership": membership, "review_form": review_form, "can_approve": bool(membership and membership.role == Membership.Role.OWNER)})


@login_required
def transaction_cases(request):
    membership = get_active_membership(request.user)
    wallet = Wallet.objects.filter(owner=request.user).first()
    if membership and membership.role in MANAGER_ROLES:
        cases = TransactionCase.objects.filter(business=membership.business)
        entries = LedgerEntry.objects.filter(business=membership.business)
        title = "Transaktionen und Prüffälle der Verwaltung"
        role_context = "management"
    elif membership and membership.role in STAFF_ROLES:
        cases = TransactionCase.objects.filter(business=membership.business).filter(Q(opened_by=request.user) | Q(ledger_entry__performed_by=request.user)).distinct()
        entries = LedgerEntry.objects.filter(business=membership.business, performed_by=request.user)
        title = "Meine Zahlungen und Korrekturanfragen"
        role_context = "staff"
    elif wallet:
        cases = TransactionCase.objects.filter(wallet=wallet)
        entries = LedgerEntry.objects.filter(wallet=wallet)
        title = "Meine Transaktionen und Prüffälle"
        role_context = "customer"
    else:
        raise PermissionDenied
    cases = cases.select_related("wallet", "ledger_entry", "location", "opened_by", "reviewed_by")[:250]
    entries = entries.select_related("wallet", "location", "performed_by").prefetch_related("transaction_cases")[:150]
    return render(request, "cards/transaction_case_list.html", {"cases": cases, "entries": entries, "title": title, "role_context": role_context})


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
            review_transaction_case(transaction_case=transaction_case, reviewer=request.user, action=form.cleaned_data["action"], manager_note=form.cleaned_data.get("manager_note", ""), approved_amount=form.cleaned_data.get("approved_amount"), ip_address=client_ip(request))
        except (ValidationError, PermissionDenied) as exc:
            detail = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            messages.error(request, detail)
        else:
            messages.success(request, "Der Transaktionsfall wurde aktualisiert.")
    else:
        messages.error(request, "Bitte die markierten Angaben prüfen.")
    return redirect("transaction_case_detail", case_id=transaction_case.pk)
