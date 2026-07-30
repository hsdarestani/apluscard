import logging

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .account_deletion import (
    DELETION_COMPLETION_DAYS,
    complete_account_deletion,
    send_deletion_received_email,
)
from .legal_forms import (
    AccountDeletionRequestForm,
    AuthenticatedAccountDeletionForm,
    CurrentLegalAcceptanceForm,
    LegalAppleProfileCompletionForm,
    LegalConfigurationForm,
    LegalCustomerRegistrationForm,
    PrivacyChoicesForm,
)
from .legal_models import AccountDeletionRequest, LegalAcceptance, PrivacyPreference
from .legal_services import client_ip, get_legal_configuration, has_current_acceptances, record_legal_acceptances, wallet_for_customer
from .models import Business, MemberProfile, Wallet
from .services import OWNER_ROLES, get_active_membership, require_role
from .views import _send_verification_email

logger = logging.getLogger(__name__)


def _business_for_public_page(business_slug=None):
    slug = business_slug or settings.DEFAULT_BUSINESS_SLUG
    return get_object_or_404(Business, slug=slug, is_active=True)


def _legal_context(business):
    configuration = get_legal_configuration(business)
    missing = []
    if not configuration.controller_name:
        missing.append("Verantwortliches Unternehmen")
    if not configuration.controller_address:
        missing.append("Geschäftsanschrift")
    if not configuration.contact_email:
        missing.append("Kontakt-E-Mail")
    if not configuration.privacy_email:
        missing.append("Datenschutz-E-Mail")
    return {"business": business, "legal": configuration, "locations": business.locations.filter(is_active=True), "legal_information_incomplete": missing}


def terms(request, business_slug=None):
    return render(request, "cards/legal/terms.html", _legal_context(_business_for_public_page(business_slug)))


def privacy_policy(request, business_slug=None):
    return render(request, "cards/legal/privacy.html", _legal_context(_business_for_public_page(business_slug)))


def imprint(request, business_slug=None):
    return render(request, "cards/legal/imprint.html", _legal_context(_business_for_public_page(business_slug)))


@transaction.atomic
def register_customer(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    business = Business.objects.filter(slug=settings.DEFAULT_BUSINESS_SLUG, is_active=True).first()
    if business is None:
        messages.error(request, "Die Registrierung ist momentan nicht verfügbar. Bitte das Lounge-Team kontaktieren.")
        return redirect("login")

    form = LegalCustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        MemberProfile.objects.create(user=user, birth_date=form.cleaned_data["birth_date"], age_confirmed=form.cleaned_data["age_confirmed"], email_verified=False)
        display_name = f"{user.first_name} {user.last_name}".strip() or user.email
        Wallet.objects.create(business=business, owner=user, display_name=display_name, phone=form.cleaned_data["phone"], email=user.email)
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        record_legal_acceptances(
            user=user,
            business=business,
            request=request,
            source=LegalAcceptance.Source.REGISTRATION,
            marketing_push=form.cleaned_data.get("marketing_push_consent", False),
            marketing_email=form.cleaned_data.get("marketing_email_consent", False),
        )
        if _send_verification_email(request, user):
            messages.success(request, "Deine Mitgliedskarte ist erstellt. Bitte bestätige jetzt deine E-Mail-Adresse.")
        else:
            messages.warning(request, "Deine Mitgliedskarte ist erstellt. Die Bestätigungs-E-Mail konnte gerade nicht gesendet werden. Bitte nutze in der App ‚Link erneut senden‘.")
        return redirect("customer_dashboard")

    return render(request, "cards/register.html", {"form": form, "business": business})


@login_required
@transaction.atomic
def complete_customer_profile(request):
    if request.user.business_memberships.filter(is_active=True).exists() or Wallet.objects.filter(owner=request.user).exists():
        return redirect("dashboard")
    if not SocialAccount.objects.filter(user=request.user, provider="apple").exists():
        messages.error(request, "Dieses Profil kann nur nach einer Anmeldung mit Apple vervollständigt werden.")
        return redirect("login")

    business = Business.objects.filter(slug=settings.DEFAULT_BUSINESS_SLUG, is_active=True).first()
    if business is None:
        messages.error(request, "Die Registrierung ist momentan nicht verfügbar. Bitte wende dich an das SAMS-Team.")
        return redirect("login")

    form = LegalAppleProfileCompletionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        name = f"{user.first_name} {user.last_name}".strip() or user.email
        Wallet.objects.get_or_create(business=business, owner=user, defaults={"display_name": name, "phone": form.cleaned_data["phone"], "email": user.email})
        record_legal_acceptances(
            user=user,
            business=business,
            request=request,
            source=LegalAcceptance.Source.APPLE,
            marketing_push=form.cleaned_data.get("marketing_push_consent", False),
            marketing_email=form.cleaned_data.get("marketing_email_consent", False),
        )
        messages.success(request, "Dein Mitgliedskonto und deine digitale Mitgliedskarte sind jetzt bereit.")
        return redirect("customer_dashboard")

    return render(request, "cards/complete_customer_profile.html", {"form": form, "business": business})


@login_required
def legal_acceptance(request):
    wallet = wallet_for_customer(request.user)
    if wallet is None:
        return redirect("dashboard")
    configuration = get_legal_configuration(wallet.business)
    if has_current_acceptances(request.user, wallet.business):
        return redirect("dashboard")

    form = CurrentLegalAcceptanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        preference = PrivacyPreference.objects.filter(user=request.user, business=wallet.business).first()
        record_legal_acceptances(
            user=request.user,
            business=wallet.business,
            request=request,
            source=LegalAcceptance.Source.RECONFIRMATION,
            marketing_push=preference.marketing_push_enabled if preference else False,
            marketing_email=preference.marketing_email_enabled if preference else False,
        )
        messages.success(request, "Die aktuellen Rechtstexte wurden bestätigt.")
        return redirect("dashboard")
    return render(request, "cards/legal/acceptance.html", {"form": form, "business": wallet.business, "legal": configuration})


@login_required
def privacy_choices(request):
    wallet = wallet_for_customer(request.user)
    if wallet is None:
        raise PermissionDenied
    preference, _ = PrivacyPreference.objects.get_or_create(user=request.user, business=wallet.business)
    originally_enabled = preference.marketing_push_enabled or preference.marketing_email_enabled
    form_data = request.POST if request.method == "POST" else None
    form = PrivacyChoicesForm(form_data, instance=preference)
    if request.method == "POST" and form.is_valid():
        preference = form.save(commit=False)
        currently_enabled = preference.marketing_push_enabled or preference.marketing_email_enabled
        if currently_enabled and not originally_enabled:
            preference.consented_at = timezone.now()
            preference.withdrawn_at = None
        elif originally_enabled and not currently_enabled:
            preference.withdrawn_at = timezone.now()
        preference.save()
        messages.success(request, "Deine Datenschutz-Einstellungen wurden gespeichert.")
        return redirect("privacy_choices")
    return render(request, "cards/legal/privacy_choices.html", {"form": form, "business": wallet.business, "preference": preference})


def _send_deletion_receipt_safely(deletion_request):
    try:
        send_deletion_received_email(deletion_request)
    except Exception:
        logger.exception("Deletion receipt email failed for reference=%s", deletion_request.reference_number)


def account_deletion(request, business_slug=None):
    business = _business_for_public_page(business_slug)
    wallet = None
    reference = None
    submitted = False
    authenticated_flow = False

    if request.user.is_authenticated:
        wallet = Wallet.objects.filter(owner=request.user, business=business).first()
        if wallet is not None and not request.user.business_memberships.filter(is_active=True).exists():
            authenticated_flow = True
            form = AuthenticatedAccountDeletionForm(request.POST or None)
            if request.method == "POST" and form.is_valid():
                email = (request.user.email or wallet.email).strip().lower()
                deletion_request, created = AccountDeletionRequest.objects.get_or_create(
                    business=business,
                    user=request.user,
                    status__in=[AccountDeletionRequest.Status.RECEIVED, AccountDeletionRequest.Status.PROCESSING],
                    defaults={
                        "wallet": wallet,
                        "email": email,
                        "member_number": wallet.member_number,
                        "status": AccountDeletionRequest.Status.PROCESSING,
                        "requested_ip": client_ip(request),
                        "requested_user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
                    },
                )
                if not created:
                    deletion_request.wallet = wallet
                    deletion_request.email = email
                    deletion_request.member_number = wallet.member_number
                    deletion_request.status = AccountDeletionRequest.Status.PROCESSING
                    deletion_request.requested_ip = client_ip(request)
                    deletion_request.requested_user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
                    deletion_request.save(
                        update_fields=[
                            "wallet",
                            "email",
                            "member_number",
                            "status",
                            "requested_ip",
                            "requested_user_agent",
                        ]
                    )
                reference = deletion_request.reference_number
                submitted = True
                _send_deletion_receipt_safely(deletion_request)
                auth_logout(request)
                form = AuthenticatedAccountDeletionForm()
        else:
            form = AccountDeletionRequestForm(request.POST or None)
    else:
        form = AccountDeletionRequestForm(request.POST or None)

    if not authenticated_flow and request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        member_number = form.cleaned_data.get("member_number", "")
        existing = AccountDeletionRequest.objects.filter(
            business=business,
            email__iexact=email,
            status__in=[AccountDeletionRequest.Status.RECEIVED, AccountDeletionRequest.Status.PROCESSING],
        ).first()
        if existing:
            deletion_request = existing
        else:
            linked_wallet = None
            if member_number:
                linked_wallet = Wallet.objects.filter(
                    business=business,
                    member_number=member_number,
                ).filter(Q(email__iexact=email) | Q(owner__email__iexact=email)).select_related("owner").first()
            deletion_request = form.save(commit=False)
            deletion_request.business = business
            deletion_request.user = linked_wallet.owner if linked_wallet else None
            deletion_request.wallet = linked_wallet
            deletion_request.email = email
            deletion_request.member_number = member_number
            deletion_request.requested_ip = client_ip(request)
            deletion_request.requested_user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
            deletion_request.save()
        reference = deletion_request.reference_number
        submitted = True
        _send_deletion_receipt_safely(deletion_request)
        form = AccountDeletionRequestForm()

    return render(
        request,
        "cards/legal/account_deletion.html",
        {
            "form": form,
            "business": business,
            "reference": reference,
            "wallet": wallet,
            "submitted": submitted,
            "authenticated_flow": authenticated_flow,
            "completion_days": DELETION_COMPLETION_DAYS,
        },
    )


@login_required
def manager_legal(request):
    membership = get_active_membership(request.user)
    if not membership:
        raise PermissionDenied
    require_role(request.user, membership.business, OWNER_ROLES)
    configuration = get_legal_configuration(membership.business)
    form = LegalConfigurationForm(request.POST or None, instance=configuration)

    if request.method == "POST":
        action = request.POST.get("action", "configuration")
        if action == "configuration" and form.is_valid():
            form.save()
            messages.success(request, "Rechtstexte und Anbieterangaben wurden gespeichert.")
            return redirect("manager_legal")
        if action == "deletion-status":
            deletion_request = get_object_or_404(AccountDeletionRequest, pk=request.POST.get("request_id"), business=membership.business)
            status = request.POST.get("status")
            if status == AccountDeletionRequest.Status.COMPLETED:
                result = complete_account_deletion(deletion_request)
                messages.success(
                    request,
                    f"Kontolöschung {result['reference']} abgeschlossen. Direkt identifizierende Daten wurden entfernt und die Bestätigung wurde versendet.",
                )
                return redirect("manager_legal")
            if status not in [AccountDeletionRequest.Status.RECEIVED, AccountDeletionRequest.Status.PROCESSING]:
                raise PermissionDenied
            deletion_request.status = status
            deletion_request.internal_note = request.POST.get("internal_note", "").strip()
            deletion_request.completed_at = None
            deletion_request.save(update_fields=["status", "internal_note", "completed_at"])
            messages.success(request, "Status des Löschantrags wurde aktualisiert.")
            return redirect("manager_legal")
        messages.error(request, "Bitte die markierten Angaben prüfen.")

    deletion_requests = membership.business.account_deletion_requests.select_related("user", "wallet")[:100]
    return render(request, "cards/legal/manager_legal.html", {"form": form, "business": membership.business, "legal": configuration, "deletion_requests": deletion_requests})
