import hashlib

from django.db import transaction
from django.utils import timezone

from .legal_models import LegalAcceptance, LegalConfiguration, PrivacyPreference
from .models import Wallet


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def email_hash(email):
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()


def get_legal_configuration(business):
    defaults = {"app_display_name": business.name, "controller_name": business.name}
    try:
        app_settings = business.app_settings
    except Exception:
        app_settings = None
    if app_settings:
        defaults.update(
            {
                "controller_name": app_settings.legal_name or business.name,
                "controller_address": app_settings.legal_address,
                "vat_id": app_settings.vat_id,
            }
        )
    if not defaults.get("controller_address"):
        first_location = business.locations.order_by("position", "name").first()
        if first_location:
            defaults["controller_address"] = first_location.address
    configuration, _ = LegalConfiguration.objects.get_or_create(
        business=business,
        defaults=defaults,
    )
    return configuration


def current_versions(business):
    configuration = get_legal_configuration(business)
    return {
        LegalAcceptance.DocumentType.TERMS: configuration.terms_version,
        LegalAcceptance.DocumentType.PRIVACY: configuration.privacy_version,
    }


def has_current_acceptances(user, business):
    if not user or not user.is_authenticated:
        return False
    versions = current_versions(business)
    accepted = set(
        LegalAcceptance.objects.filter(
            user=user,
            business=business,
            document_type__in=versions.keys(),
        ).values_list("document_type", "version")
    )
    return all((document_type, version) in accepted for document_type, version in versions.items())


@transaction.atomic
def record_legal_acceptances(*, user, business, request, source, marketing_push=False, marketing_email=False):
    wallet = Wallet.objects.filter(owner=user, business=business).first()
    versions = current_versions(business)
    common = {
        "source": source,
        "email_hash": email_hash(user.email),
        "member_number": wallet.member_number if wallet else "",
        "ip_address": client_ip(request),
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
    }
    for document_type, version in versions.items():
        LegalAcceptance.objects.update_or_create(
            user=user,
            business=business,
            document_type=document_type,
            version=version,
            defaults=common,
        )

    consented = bool(marketing_push or marketing_email)
    preference, _ = PrivacyPreference.objects.get_or_create(user=user, business=business)
    preference.marketing_push_enabled = bool(marketing_push)
    preference.marketing_email_enabled = bool(marketing_email)
    if consented:
        preference.consented_at = timezone.now()
        preference.withdrawn_at = None
    elif preference.marketing_push_enabled or preference.marketing_email_enabled:
        preference.withdrawn_at = timezone.now()
    preference.save()
    return preference


def wallet_for_customer(user):
    return Wallet.objects.select_related("business").filter(owner=user).first()
