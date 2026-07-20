from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CustomerRegistrationForm, ManagerMoneyActionForm, MoneyActionForm, WalletCreateForm
from .models import Business, LedgerEntry, Wallet
from .services import MANAGER_ROLES, STAFF_ROLES, get_active_membership, post_wallet_entry, require_role, set_wallet_status


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "cards/landing.html")


@transaction.atomic
def register_customer(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    business = Business.objects.filter(slug=settings.DEFAULT_BUSINESS_SLUG, is_active=True).first()
    if business is None:
        messages.error(request, "Die Registrierung ist momentan nicht verfügbar. Bitte das Lounge-Team kontaktieren.")
        return redirect("login")

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            display_name = f"{user.first_name} {user.last_name}".strip() or user.email
            Wallet.objects.create(
                business=business,
                owner=user,
                display_name=display_name,
                phone=form.cleaned_data["phone"],
                email=user.email,
            )
            auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Willkommen im SAMS Club Lounge. Deine digitale Member Card ist bereit.")
            return redirect("customer_dashboard")
    else:
        form = CustomerRegistrationForm()

    return render(request, "cards/register.html", {"form": form, "business": business})


def health(request):
    return JsonResponse({"status": "ok"})


def manifest(request):
    return JsonResponse({
        "name": "SAMS Club Lounge · powered by A+",
        "short_name": "SAMS Lounge",
        "description": "Member Wallet, Cashless Payment und Lounge Experience.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#05030b",
        "theme_color": "#09050f",
        "categories": ["lifestyle", "finance", "food"],
        "icons": [{"src": "/static/cards/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
    })


def service_worker(request):
    content = """
const CACHE = 'sams-lounge-v4';
const CORE = ['/', '/accounts/register/', '/static/cards/app.css', '/static/cards/app.js', '/static/cards/icon.svg', '/manifest.webmanifest'];
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE)));
});
self.addEventListener('activate', event => event.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())
));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(response => response || caches.match('/'))));
});
""".strip()
    response = HttpResponse(content, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@login_required
def dashboard(request):
    membership = get_active_membership(request.user)
    if membership:
        if membership.role in MANAGER_ROLES:
            return redirect("manager_dashboard")
        return redirect("staff_dashboard")
    if Wallet.objects.filter(owner=request.user).exists():
        return redirect("customer_dashboard")
    raise PermissionDenied("Für dieses Konto wurde noch keine Karte eingerichtet.")


@login_required
def customer_dashboard(request):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), owner=request.user)
    entries = wallet.ledger_entries.select_related("performed_by")[:30]
    return render(request, "cards/customer_dashboard.html", {"wallet": wallet, "entries": entries})


@login_required
def staff_dashboard(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in STAFF_ROLES:
        raise PermissionDenied
    recent_entries = LedgerEntry.objects.filter(
        business=membership.business,
        performed_by=request.user,
        entry_type=LedgerEntry.Type.PURCHASE,
    ).select_related("wallet")[:20]
    return render(request, "cards/staff_dashboard.html", {
        "membership": membership,
        "form": MoneyActionForm(),
        "recent_entries": recent_entries,
    })


@login_required
@require_POST
def staff_charge(request):
    form = MoneyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Eingaben prüfen.")
        return redirect("staff_dashboard")
    wallet = get_object_or_404(Wallet.objects.select_related("business"), qr_token=form.cleaned_data["wallet_token"])
    require_role(request.user, wallet.business, STAFF_ROLES)
    try:
        entry = post_wallet_entry(
            wallet=wallet,
            entry_type=LedgerEntry.Type.PURCHASE,
            amount=form.cleaned_data["amount"],
            actor=request.user,
            description=form.cleaned_data["description"],
            order_reference=form.cleaned_data["order_reference"],
            ip_address=client_ip(request),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"{abs(entry.amount):.2f} € von {wallet.display_name} abgebucht. Beleg {entry.bill_number} wurde erstellt.")
    return redirect("staff_dashboard")


@login_required
def manager_dashboard(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    wallets = Wallet.objects.filter(business=membership.business)
    query = request.GET.get("q", "").strip()
    if query:
        wallet_filter = (
            Q(display_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
            | Q(member_number__icontains=query)
        )
        try:
            wallet_filter |= Q(qr_token=UUID(query))
        except (ValueError, TypeError):
            pass
        wallets = wallets.filter(wallet_filter)
    totals = wallets.aggregate(total_balance=Sum("balance"))
    recent_entries = LedgerEntry.objects.filter(business=membership.business).select_related("wallet", "performed_by")[:25]
    return render(request, "cards/manager_dashboard.html", {
        "membership": membership,
        "wallets": wallets[:100],
        "wallet_count": Wallet.objects.filter(business=membership.business).count(),
        "total_balance": totals["total_balance"] or 0,
        "recent_entries": recent_entries,
        "create_form": WalletCreateForm(),
        "query": query,
    })


@login_required
@require_POST
def manager_wallet_create(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    form = WalletCreateForm(request.POST)
    if form.is_valid():
        wallet = form.save(commit=False)
        wallet.business = membership.business
        wallet.save()
        messages.success(request, f"Kundenkarte {wallet.member_number} wurde erstellt.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)
    messages.error(request, "Kundenkarte konnte nicht erstellt werden.")
    return redirect("manager_dashboard")


@login_required
def manager_wallet_detail(request, wallet_id):
    wallet = get_object_or_404(Wallet.objects.select_related("business", "owner"), pk=wallet_id)
    require_role(request.user, wallet.business, MANAGER_ROLES)
    entries = wallet.ledger_entries.select_related("performed_by")[:100]
    return render(request, "cards/manager_wallet_detail.html", {
        "wallet": wallet,
        "entries": entries,
        "action_form": ManagerMoneyActionForm(),
    })


def _manager_money_action(request, wallet_id, entry_type):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), pk=wallet_id)
    require_role(request.user, wallet.business, MANAGER_ROLES)
    form = ManagerMoneyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Betrag und Angaben prüfen.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)
    try:
        entry = post_wallet_entry(
            wallet=wallet,
            entry_type=entry_type,
            amount=form.cleaned_data["amount"],
            actor=request.user,
            description=form.cleaned_data["description"],
            order_reference=form.cleaned_data["order_reference"],
            ip_address=client_ip(request),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        label = "aufgeladen" if entry_type == LedgerEntry.Type.TOPUP else "erstattet"
        messages.success(request, f"{abs(entry.amount):.2f} € wurden {label}. Beleg {entry.bill_number} wurde erstellt.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
@require_POST
def manager_topup(request, wallet_id):
    return _manager_money_action(request, wallet_id, LedgerEntry.Type.TOPUP)


@login_required
@require_POST
def manager_refund(request, wallet_id):
    return _manager_money_action(request, wallet_id, LedgerEntry.Type.REFUND)


@login_required
@require_POST
def manager_wallet_status(request, wallet_id):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), pk=wallet_id)
    require_role(request.user, wallet.business, MANAGER_ROLES)
    try:
        set_wallet_status(
            wallet=wallet,
            status=request.POST.get("status", ""),
            actor=request.user,
            ip_address=client_ip(request),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Kartenstatus wurde aktualisiert.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
def bill_detail(request, entry_id):
    entry = get_object_or_404(
        LedgerEntry.objects.select_related("business", "wallet", "wallet__owner", "performed_by"),
        pk=entry_id,
    )
    is_customer_owner = entry.wallet.owner_id == request.user.id
    if not is_customer_owner:
        require_role(request.user, entry.business, STAFF_ROLES)
    return render(request, "cards/bill_detail.html", {"entry": entry, "wallet": entry.wallet})
