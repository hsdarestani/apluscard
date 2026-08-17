import logging
from datetime import timedelta
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .email_verification_models import EmailVerificationAttempt
from .emailing import send_verification_email, verification_token_hash
from .models import MemberProfile

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = "sams-member-email-verification"
EMAIL_VERIFICATION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _find_attempt(request, token):
    """Resolve the exact persisted attempt from the opaque link secret."""
    token_hash = verification_token_hash(token)
    attempt_ref = (request.GET.get("attempt") or "").strip()
    if attempt_ref:
        try:
            attempt_id = UUID(attempt_ref)
        except (TypeError, ValueError):
            attempt_id = None
        if attempt_id is not None:
            attempt = (
                EmailVerificationAttempt.objects.select_related("user")
                .filter(pk=attempt_id, token_hash=token_hash)
                .first()
            )
            if attempt is not None:
                return attempt

    return (
        EmailVerificationAttempt.objects.select_related("user")
        .filter(token_hash=token_hash)
        .order_by("-created_at")
        .first()
    )


def _record_click(attempt):
    if attempt is None:
        return
    now = timezone.now()
    attempt.click_count += 1
    if attempt.clicked_at is None:
        attempt.clicked_at = now
    if attempt.status in {
        EmailVerificationAttempt.Status.PENDING,
        EmailVerificationAttempt.Status.ACCEPTED,
    }:
        attempt.status = EmailVerificationAttempt.Status.CLICKED
    attempt.save(update_fields=["click_count", "clicked_at", "status", "updated_at"])


def _record_failure(attempt, status, error_class, error_detail):
    if attempt is None:
        return
    attempt.status = status
    attempt.error_class = error_class[:120]
    attempt.error_detail = error_detail[:4000]
    attempt.save(update_fields=["status", "error_class", "error_detail", "updated_at"])


def _profile_from_attempt(attempt):
    if attempt is None or attempt.user_id is None:
        return None
    email = (attempt.email or "").strip()
    if not email:
        return None
    return (
        MemberProfile.objects.select_related("user")
        .filter(
            user_id=attempt.user_id,
            user__email__iexact=email,
            user__is_active=True,
        )
        .first()
    )


def _profile_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("uid")
    email = (payload.get("email") or "").strip()
    if not user_id or not email:
        return None
    return (
        MemberProfile.objects.select_related("user")
        .filter(
            user_id=user_id,
            user__email__iexact=email,
            user__is_active=True,
        )
        .first()
    )


def _login_verified_member(request, profile):
    if not request.user.is_authenticated:
        auth_login(
            request,
            profile.user,
            backend="django.contrib.auth.backends.ModelBackend",
        )


def _confirm_profile(profile, attempt):
    now = timezone.now()
    with transaction.atomic():
        locked_profile = (
            MemberProfile.objects.select_for_update()
            .select_related("user")
            .get(pk=profile.pk)
        )
        if not locked_profile.email_verified:
            locked_profile.email_verified = True
            locked_profile.email_verified_at = now
            locked_profile.save(update_fields=["email_verified", "email_verified_at"])
        elif locked_profile.email_verified_at is None:
            locked_profile.email_verified_at = now
            locked_profile.save(update_fields=["email_verified_at"])

        if attempt is not None:
            EmailVerificationAttempt.objects.filter(pk=attempt.pk).update(
                status=EmailVerificationAttempt.Status.CONFIRMED,
                confirmed_at=attempt.confirmed_at or now,
                error_class="",
                error_detail="",
                updated_at=now,
            )

    return locked_profile


def _send_recovery_link(request, profile, attempt):
    if attempt is not None:
        _record_failure(
            attempt,
            EmailVerificationAttempt.Status.EXPIRED,
            "VerificationExpired",
            "Verification attempt exceeded the configured validity window.",
        )

    if profile.email_verified:
        _login_verified_member(request, profile)
        messages.success(request, "Deine E-Mail-Adresse ist bereits bestätigt.")
        return redirect("dashboard")

    try:
        send_verification_email(
            request,
            profile.user,
            trigger=EmailVerificationAttempt.Trigger.RESEND,
        )
    except Exception:
        logger.exception("Expired verification recovery failed user_id=%s", profile.user_id)
        messages.error(request, "Der alte Link ist abgelaufen. Bitte versuche es erneut.")
    else:
        messages.info(
            request,
            "Der alte Link war abgelaufen. Wir haben dir automatisch einen neuen Bestätigungslink geschickt.",
        )

    if request.user.is_authenticated and request.user.pk == profile.user_id:
        return redirect("customer_dashboard")
    return redirect("login")


def _verify_persisted_attempt(request, attempt):
    profile = _profile_from_attempt(attempt)
    if profile is None:
        _record_failure(
            attempt,
            EmailVerificationAttempt.Status.INVALID,
            "ProfileMismatch",
            "The verification attempt no longer matches an active user and email address.",
        )
        messages.error(request, "Der Bestätigungslink passt nicht mehr zu diesem Konto.")
        return redirect("login")

    expires_at = attempt.created_at + timedelta(seconds=EMAIL_VERIFICATION_MAX_AGE_SECONDS)
    if timezone.now() > expires_at:
        return _send_recovery_link(request, profile, attempt)

    _record_click(attempt)
    profile = _confirm_profile(profile, attempt)
    _login_verified_member(request, profile)
    logger.info("Email verified attempt_id=%s user_id=%s", attempt.pk, profile.user_id)
    messages.success(request, "E-Mail bestätigt – deine Member Card ist jetzt freigeschaltet.")
    return redirect("dashboard")


def _verify_legacy_signed_token(request, token):
    """Keep pre-audit verification links working while new links are DB-backed."""
    try:
        payload = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=EMAIL_VERIFICATION_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired:
        try:
            payload = signing.loads(token, salt=EMAIL_VERIFICATION_SALT)
        except signing.BadSignature:
            messages.error(request, "Der Bestätigungslink ist ungültig.")
            return redirect("login")
        profile = _profile_from_payload(payload)
        if profile is None:
            messages.error(request, "Der Bestätigungslink passt nicht mehr zu diesem Konto.")
            return redirect("login")
        return _send_recovery_link(request, profile, None)
    except signing.BadSignature:
        messages.error(request, "Der Bestätigungslink ist ungültig.")
        return redirect("login")

    profile = _profile_from_payload(payload)
    if profile is None:
        messages.error(request, "Der Bestätigungslink passt nicht mehr zu diesem Konto.")
        return redirect("login")

    profile = _confirm_profile(profile, None)
    _login_verified_member(request, profile)
    logger.info("Legacy email verification succeeded user_id=%s", profile.user_id)
    messages.success(request, "E-Mail bestätigt – deine Member Card ist jetzt freigeschaltet.")
    return redirect("dashboard")


def verify_email(request, token):
    attempt = _find_attempt(request, token)
    if attempt is not None:
        return _verify_persisted_attempt(request, attempt)
    return _verify_legacy_signed_token(request, token)


@login_required
@require_POST
def resend_verification(request):
    profile = getattr(request.user, "member_profile", None)
    if not profile:
        raise PermissionDenied
    if profile.email_verified:
        messages.info(request, "Deine E-Mail-Adresse ist bereits bestätigt.")
        return redirect("customer_dashboard")

    try:
        send_verification_email(request, request.user)
    except Exception:
        logger.exception("Verification resend failed user_id=%s", request.user.pk)
        messages.error(request, "Die E-Mail konnte nicht versendet werden. Bitte versuche es erneut.")
    else:
        messages.success(request, "Ein neuer Bestätigungslink wurde an deine E-Mail-Adresse versendet.")
    return redirect("customer_dashboard")
