import logging

from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .email_verification_signals import sync_allauth_email_address
from .models import MemberProfile
from .views import EMAIL_VERIFICATION_SALT

logger = logging.getLogger(__name__)


@transaction.atomic
def verify_email(request, token):
    """Verify the member email and reconcile django-allauth every time.

    The verification link is intentionally idempotent.  Older/imported rows can
    have MemberProfile.email_verified=True while allauth's EmailAddress.verified
    is still False.  A repeated click must repair that mismatch instead of
    returning success without changing the admin state.
    """
    try:
        payload = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=48 * 60 * 60,
        )
    except signing.BadSignature:
        messages.error(request, "Der Bestätigungslink ist ungültig oder abgelaufen.")
        return redirect("login")

    profile = get_object_or_404(
        MemberProfile.objects.select_related("user"),
        user_id=payload.get("uid"),
        user__email__iexact=payload.get("email", ""),
    )

    update_fields = []
    if not profile.email_verified:
        profile.email_verified = True
        update_fields.append("email_verified")
    if profile.email_verified_at is None:
        profile.email_verified_at = timezone.now()
        update_fields.append("email_verified_at")
    if update_fields:
        profile.save(update_fields=update_fields)

    address = sync_allauth_email_address(profile.user, verified=True)
    if address is None:
        logger.error(
            "Email verification succeeded for user_id=%s but allauth reconciliation failed",
            profile.user_id,
        )
        messages.warning(
            request,
            "Deine E-Mail-Adresse wurde bestätigt, der Kontostatus konnte aber nicht vollständig synchronisiert werden. Bitte das SAMS-Team kontaktieren.",
        )
    else:
        logger.info(
            "Email verification completed and reconciled for user_id=%s email_address_id=%s",
            profile.user_id,
            address.pk,
        )
        messages.success(request, "Deine E-Mail-Adresse wurde erfolgreich bestätigt.")

    return redirect("dashboard" if request.user.is_authenticated else "login")
