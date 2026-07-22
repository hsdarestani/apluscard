import logging
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .emailing import send_verification_email
from .forms import BusinessSettingsForm, CustomerRegistrationForm, LocationForm, ManagerChargeForm, ManagerMoneyActionForm, MoneyActionForm, OfferForm, PaymentConfirmForm, WalletCreateForm
from .models import AppNotification, Business, LedgerEntry, Location, MemberProfile, Membership, Offer, PaymentRequest, ReviewStatus, Wallet
from .services import MANAGER_ROLES, OWNER_ROLES, STAFF_ROLES, active_offers_for, create_payment_request, finalize_payment_request, get_active_membership, get_business_settings, post_wallet_entry, require_role, set_wallet_status

logger = logging.getLogger(__name__)
EMAIL_VERIFICATION_SALT = "sams-member-email-verification"


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "cards/landing.html")


def _verification_token(user):
    return signing.dumps({"uid": user.pk, "email": user.email}, salt=EMAIL_VERIFICATION_SALT)


def _send_verification_email(request, user):
    try:
        send_verification_email(request, user)
    except Exception:
        logger.exception("Verification email failed for user_id=%s", user.pk)
        return False
    return True


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
            MemberProfile.objects.create(user=user, birth_date=form.cleaned_data["birth_date"], age_confirmed=form.cleaned_data["age_confirmed"], email_verified=False)
            display_name = f"{user.first_name} {user.last_name}".strip() or user.email
            Wallet.objects.create(business=business, owner=user, display_name=display_name, phone=form.cleaned_data["phone"], email=user.email)
            auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            if _send_verification_email(request, user):
                messages.success(request, "Deine Member Card ist erstellt. Bitte bestätige jetzt deine E-Mail-Adresse.")
            else:
                messages.warning(request, "Deine Member Card ist erstellt. Die Bestätigungs-E-Mail konnte gerade nicht versendet werden. Bitte nutze gleich ‚Link erneut senden‘.")
            return redirect("customer_dashboard")
    else:
        form = CustomerRegistrationForm()
    return render(request, "cards/register.html", {"form": form, "business": business})


def verify_email(request, token):
    try:
        payload = signing.loads(token, salt=EMAIL_VERIFICATION_SALT, max_age=48 * 60 * 60)
    except signing.BadSignature:
        messages.error(request, "Der Bestätigungslink ist ungültig oder abgelaufen.")
        return redirect("login")
    profile = get_object_or_404(MemberProfile.objects.select_related("user"), user_id=payload.get("uid"), user__email__iexact=payload.get("email", ""))
    if not profile.email_verified:
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified", "email_verified_at"])
    messages.success(request, "Deine E-Mail-Adresse wurde erfolgreich bestätigt.")
    return redirect("dashboard" if request.user.is_authenticated else "login")


@login_required
@require_POST
def resend_verification(request):
    profile = getattr(request.user, "member_profile", None)
    if not profile:
        raise PermissionDenied
    if profile.email_verified:
        messages.info(request, "Deine E-Mail-Adresse ist bereits bestätigt.")
    elif _send_verification_email(request, request.user):
        messages.success(request, "Ein neuer Bestätigungslink wurde an deine E-Mail-Adresse versendet.")
    else:
        messages.error(request, "Die E-Mail konnte nicht versendet werden. Bitte das SAMS-Team kontaktieren.")
    return redirect("customer_dashboard")


def health(request):
    return JsonResponse({"status": "ok"})


def manifest(request):
    return JsonResponse({"name": "SAMS Club Lounge · powered by A+", "short_name": "SAMS Lounge", "description": "A+ Pay, Member Wallet, Loyalty und Angebote für alle SAMS Standorte.", "start_url": "/", "scope": "/", "display": "standalone", "orientation": "portrait-primary", "background_color": "#05030b", "theme_color": "#09050f", "categories": ["lifestyle", "finance", "food"], "icons": [{"src": "/static/cards/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}]})


def service_worker(request):
    content = """
const CACHE = 'sams-lounge-v5';
const CORE = ['/', '/accounts/register/', '/static/cards/app.css', '/static/cards/app.js', '/static/cards/icon.svg', '/static/cards/sams-platform.css', '/manifest.webmanifest'];
self.addEventListener('install', event => { self.skipWaiting(); event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE))); });
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => { if (event.request.method !== 'GET') return; event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(response => response || caches.match('/')))); });
""".strip()
    response = HttpResponse(content, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def _locations_for(business):
    return business.locations.filter(is_active=True)


def _active_location(request, business):
    locations = _locations_for(business)
    selected = request.session.get("active_location_id")
    if selected:
        location = locations.filter(pk=selected).first()
        if location:
            return location
    location = locations.first()
    if location:
        request.session["active_location_id"] = str(location.pk)
    return location


@login_required
@require_POST
def select_location(request):
    wallet = Wallet.objects.filter(owner=request.user).select_related("business").first()
    membership = get_active_membership(request.user)
    business = membership.business if membership else (wallet.business if wallet else None)
    if business is None:
        raise PermissionDenied
    location = get_object_or_404(Location, pk=request.POST.get("location_id"), business=business, is_active=True)
    request.session["active_location_id"] = str(location.pk)
    return redirect(request.POST.get("next") or "dashboard")


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
    wallet = get_object_or_404(Wallet.objects.select_related("business", "owner", "owner__member_profile"), owner=request.user)
    location = _active_location(request, wallet.business)
    entries = wallet.ledger_entries.select_related("performed_by", "location")[:50]
    pending_query = wallet.payment_requests.filter(status=PaymentRequest.Status.PENDING).select_related("location", "created_by")
    pending_payments = [item for item in pending_query if not item.expires_at or item.expires_at >= timezone.now()]
    settings_obj = get_business_settings(wallet.business)
    offers = active_offers_for(wallet, location)[:20]
    review_status = None
    should_request_review = False
    if location:
        review_status, _ = ReviewStatus.objects.get_or_create(wallet=wallet, location=location)
        should_request_review = not review_status.is_completed and bool(location.google_review_url) and wallet.ledger_entries.filter(location=location, entry_type=LedgerEntry.Type.PURCHASE).exists()
    return render(request, "cards/customer_dashboard.html", {"wallet": wallet, "profile": getattr(request.user, "member_profile", None), "entries": entries, "locations": _locations_for(wallet.business), "active_location": location, "pending_payments": pending_payments, "tip_choices": settings_obj.tip_choices(), "offers": offers, "review_status": review_status, "should_request_review": should_request_review})


@login_required
@require_POST
def customer_confirm_payment(request, payment_id):
    payment = get_object_or_404(PaymentRequest.objects.select_related("wallet", "business", "location"), pk=payment_id, wallet__owner=request.user)
    form = PaymentConfirmForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte einen Trinkgeldbetrag auswählen.")
        return redirect("customer_dashboard")
    try:
        payment = finalize_payment_request(payment=payment, confirmed_by=request.user, tip_amount=form.cleaned_data["tip_amount"], ip_address=client_ip(request))
    except (ValidationError, PermissionDenied) as exc:
        detail = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        messages.error(request, detail)
    else:
        messages.success(request, f"Zahlung bestätigt: {payment.base_amount:.2f} € + {payment.tip_amount:.2f} € Trinkgeld.")
    return redirect("customer_dashboard")


@login_required
@require_POST
def mark_reviewed(request, location_id):
    wallet = get_object_or_404(Wallet, owner=request.user)
    location = get_object_or_404(Location, pk=location_id, business=wallet.business)
    status, _ = ReviewStatus.objects.get_or_create(wallet=wallet, location=location)
    status.completed_at = timezone.now()
    status.save(update_fields=["completed_at"])
    messages.success(request, "Danke! Die Bewertungs-Erinnerung wird nicht mehr angezeigt.")
    return redirect("customer_dashboard")


@login_required
def staff_dashboard(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in STAFF_ROLES:
        raise PermissionDenied
    location = _active_location(request, membership.business)
    settings_obj = get_business_settings(membership.business)
    recent_entries = LedgerEntry.objects.filter(business=membership.business, performed_by=request.user, entry_type__in=[LedgerEntry.Type.PURCHASE, LedgerEntry.Type.TIP]).select_related("wallet", "location")[:30]
    return render(request, "cards/staff_dashboard.html", {"membership": membership, "form": MoneyActionForm(), "recent_entries": recent_entries, "locations": _locations_for(membership.business), "active_location": location, "settings": settings_obj, "tip_choices": settings_obj.tip_choices()})


@login_required
@require_POST
def staff_charge(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in STAFF_ROLES:
        raise PermissionDenied
    form = MoneyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Betrag, Standort und Trinkgeld prüfen.")
        return redirect("staff_dashboard")
    wallet = get_object_or_404(Wallet.objects.select_related("business", "owner", "owner__member_profile"), business=membership.business, qr_token=form.cleaned_data["wallet_token"])
    location = get_object_or_404(Location, business=membership.business, pk=form.cleaned_data["location_id"], is_active=True)
    try:
        payment = create_payment_request(wallet=wallet, location=location, actor=request.user, amount=form.cleaned_data["amount"], tip_amount=form.cleaned_data.get("tip_amount") or 0, description=form.cleaned_data["description"], order_reference=form.cleaned_data["order_reference"], ip_address=client_ip(request))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if payment.status == PaymentRequest.Status.PENDING:
            messages.success(request, f"Ausnahmsweise wurde eine Zahlungsfreigabe an Mitglied {wallet.member_number} gesendet.")
        else:
            messages.success(request, f"{payment.base_amount:.2f} € Zahlung + {payment.tip_amount:.2f} € Trinkgeld wurden abgebucht.")
    return redirect("staff_dashboard")


@login_required
def manager_dashboard(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    settings_obj = get_business_settings(membership.business)
    location = _active_location(request, membership.business)
    wallets = Wallet.objects.filter(business=membership.business)
    query = request.GET.get("q", "").strip()
    if query:
        wallet_filter = Q(display_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query) | Q(member_number__icontains=query)
        try:
            wallet_filter |= Q(qr_token=UUID(query))
        except (ValueError, TypeError):
            pass
        wallets = wallets.filter(wallet_filter)
    totals = Wallet.objects.filter(business=membership.business).aggregate(total_balance=Sum("balance"))
    recent_entries = LedgerEntry.objects.filter(business=membership.business)
    if location:
        recent_entries = recent_entries.filter(Q(location=location) | Q(location__isnull=True))
    recent_entries = recent_entries.select_related("wallet", "performed_by", "location")[:25]
    notifications = request.user.app_notifications.filter(is_read=False)[:10]
    return render(request, "cards/manager_dashboard.html", {"membership": membership, "settings": settings_obj, "wallets": wallets[:100], "wallet_count": Wallet.objects.filter(business=membership.business).count(), "total_balance": totals["total_balance"] or 0, "recent_entries": recent_entries, "create_form": WalletCreateForm(), "query": query, "locations": _locations_for(membership.business), "active_location": location, "notifications": notifications, "unread_notification_count": request.user.app_notifications.filter(is_read=False).count(), "offer_count": Offer.objects.filter(business=membership.business, is_active=True).count()})


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(AppNotification, pk=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect("manager_dashboard")


@login_required
def manager_settings(request):
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied
    is_owner = membership.role == Membership.Role.OWNER
    can_manage_content = is_owner or membership.can_manage_content
    settings_obj = get_business_settings(membership.business)
    settings_form = BusinessSettingsForm(instance=settings_obj)
    location_form = LocationForm()
    offer_form = OfferForm(business=membership.business, scheduling_enabled=True)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "settings":
            if not is_owner:
                raise PermissionDenied
            settings_form = BusinessSettingsForm(request.POST, instance=settings_obj)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, "A+ Pay Einstellungen wurden gespeichert.")
                return redirect("manager_settings")
        elif action == "location":
            if not is_owner:
                raise PermissionDenied
            location_form = LocationForm(request.POST)
            if location_form.is_valid():
                location = location_form.save(commit=False)
                location.business = membership.business
                location.save()
                messages.success(request, "Standort wurde gespeichert.")
                return redirect("manager_settings")
        elif action == "offer":
            if not can_manage_content:
                raise PermissionDenied
            offer_form = OfferForm(request.POST, request.FILES, business=membership.business, scheduling_enabled=True)
            if offer_form.is_valid():
                offer = offer_form.save(commit=False)
                offer.business = membership.business
                offer.created_by = request.user
                offer.save()
                messages.success(request, "Angebot wurde veröffentlicht.")
                return redirect("manager_settings")
        messages.error(request, "Bitte die markierten Angaben prüfen.")
    return render(request, "cards/manager_settings.html", {"membership": membership, "is_owner": is_owner, "can_manage_content": can_manage_content, "settings": settings_obj, "settings_form": settings_form, "location_form": location_form, "offer_form": offer_form, "locations": membership.business.locations.all(), "offers": membership.business.offers.select_related("location", "created_by")[:50]})


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
    wallet = get_object_or_404(Wallet.objects.select_related("business", "owner", "owner__member_profile"), pk=wallet_id)
    membership = require_role(request.user, wallet.business, MANAGER_ROLES)
    entries = wallet.ledger_entries.select_related("performed_by", "location").prefetch_related("transaction_cases")[:100]
    settings_obj = get_business_settings(wallet.business)
    return render(request, "cards/manager_wallet_detail.html", {"wallet": wallet, "entries": entries, "action_form": ManagerMoneyActionForm(), "charge_form": ManagerChargeForm(), "is_owner": membership.role == Membership.Role.OWNER, "locations": _locations_for(wallet.business), "tip_choices": settings_obj.tip_choices()})


def _manager_money_action(request, wallet_id, entry_type):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), pk=wallet_id)
    require_role(request.user, wallet.business, OWNER_ROLES)
    form = ManagerMoneyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Betrag und Angaben prüfen.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)
    try:
        entry = post_wallet_entry(wallet=wallet, entry_type=entry_type, amount=form.cleaned_data["amount"], actor=request.user, description=form.cleaned_data["description"], order_reference=form.cleaned_data["order_reference"], ip_address=client_ip(request))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        if entry_type == LedgerEntry.Type.TOPUP:
            messages.success(request, f"{entry.amount:.2f} € wurden als neues Prepaid-Guthaben hinzugefügt. Beleg {entry.bill_number}.")
        else:
            messages.success(request, f"{entry.amount:.2f} € wurden als Rückgabe/Korrektur gutgeschrieben. Beleg {entry.bill_number}.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
@require_POST
def manager_charge(request, wallet_id):
    wallet = get_object_or_404(Wallet.objects.select_related("business", "owner", "owner__member_profile"), pk=wallet_id)
    require_role(request.user, wallet.business, OWNER_ROLES)
    form = ManagerChargeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Standort, Betrag und Trinkgeld prüfen.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)
    location = get_object_or_404(Location, pk=form.cleaned_data["location_id"], business=wallet.business, is_active=True)
    try:
        payment = create_payment_request(wallet=wallet, location=location, actor=request.user, amount=form.cleaned_data["amount"], tip_amount=form.cleaned_data.get("tip_amount") or 0, description=form.cleaned_data["description"], order_reference=form.cleaned_data["order_reference"], ip_address=client_ip(request), force_immediate=True)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"{payment.base_amount:.2f} € Zahlung + {payment.tip_amount:.2f} € Trinkgeld wurden sofort abgebucht.")
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
        set_wallet_status(wallet=wallet, status=request.POST.get("status", ""), actor=request.user, ip_address=client_ip(request))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Kartenstatus wurde aktualisiert.")
    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
def bill_detail(request, entry_id):
    entry = get_object_or_404(LedgerEntry.objects.select_related("business", "location", "wallet", "wallet__owner", "performed_by", "payment_request"), pk=entry_id)
    is_customer_owner = entry.wallet.owner_id == request.user.id
    if not is_customer_owner:
        require_role(request.user, entry.business, STAFF_ROLES)
    settings_obj = get_business_settings(entry.business)
    return render(request, "cards/bill_detail.html", {"entry": entry, "wallet": entry.wallet, "settings": settings_obj})
