import logging
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .email_verification_models import EmailVerificationAttempt
from .emailing import send_verification_email, verification_token_hash
from .models import MemberProfile

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = "sams-member-email-verification"
EMAIL_VERIFICATION_MAX_AGE_SECONDS = 48 * 60 * 60


def _find_attempt(request, token):
    attempt_ref = (request.GET.get("attempt") or "").strip()
    if attempt_ref:
        try:
            attempt_id = UUID(attempt_ref)
        except (TypeError, ValueError):
            attempt_id = None
        if attempt_id is not None:
            attempt = EmailVerificationAttempt.objects.select_related("user").filter(pk=attempt_id).first()
            if attempt is not None:
                return attempt

    return (
        EmailVerificationAttempt.objects.select_related("user")
        .filter(token_hash=verification_token_hash(token))
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


def verify_email(request, token):
    attempt = _find_attempt(request, token)
    _record_click(attempt)

    try:
        payload = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=EMAIL_VERIFICATION_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as exc:
        _record_failure(
            attempt,
            EmailVerificationAttempt.Status.EXPIRED,
            exc.__class__.__name__,
            str(exc) or "Verification token expired.",
        )
        logger.warning("Verification link expired attempt_id=%s", getattr(attempt, "pk", None))
        messages.error(request, "Der Bestätigungslink ist abgelaufen. Bitte fordere einen neuen Link an.")
        return redirect("login")
    except signing.BadSignature as exc:
        _record_failure(
            attempt,
            EmailVerificationAttempt.Status.INVALID,
            exc.__class__.__name__,
            str(exc) or "Verification token signature is invalid.",
        )
        logger.warning("Verification link invalid attempt_id=%s", getattr(attempt, "pk", None))
        messages.error(request, "Der Bestätigungslink ist ungültig. Bitte fordere einen neuen Link an.")
        return redirect("login")

    user_id = payload.get("uid")
    email = (payload.get("email") or "").strip()
    profile = (
        MemberProfile.objects.select_related("user")
        .filter(user_id=user_id, user__email__iexact=email)
        .first()
    )
    if profile is None:
        _record_failure(
            attempt,
            EmailVerificationAttempt.Status.INVALID,
            "ProfileMismatch",
            "The signed user/email no longer matches an active member profile.",
        )
        logger.warning(
            "Verification profile mismatch attempt_id=%s user_id=%s",
            getattr(attempt, "pk", None),
            user_id,
        )
        messages.error(request, "Der Bestätigungslink passt nicht mehr zu diesem Konto. Bitte fordere einen neuen Link an.")
        return redirect("login")

    if attempt is not None:
        if attempt.user_id and attempt.user_id != profile.user_id:
            _record_failure(
                attempt,
                EmailVerificationAttempt.Status.INVALID,
                "AttemptUserMismatch",
                "Attempt reference and signed token point to different users.",
            )
            messages.error(request, "Der Bestätigungslink ist ungültig. Bitte fordere einen neuen Link an.")
            return redirect("login")
        if attempt.email and attempt.email.lower() != email.lower():
            _record_failure(
                attempt,
                EmailVerificationAttempt.Status.INVALID,
                "AttemptEmailMismatch",
                "Attempt reference and signed token point to different email addresses.",
            )
            messages.error(request, "Der Bestätigungslink ist ungültig. Bitte fordere einen neuen Link an.")
            return redirect("login")

    now = timezone.now()
    if not profile.email_verified:
        profile.email_verified = True
        profile.email_verified_at = now
        profile.save(update_fields=["email_verified", "email_verified_at"])
    elif profile.email_verified_at is None:
        profile.email_verified_at = now
        profile.save(update_fields=["email_verified_at"])

    if attempt is not None:
        attempt.status = EmailVerificationAttempt.Status.CONFIRMED
        attempt.confirmed_at = attempt.confirmed_at or now
        attempt.error_class = ""
        attempt.error_detail = ""
        attempt.save(
            update_fields=[
                "status",
                "confirmed_at",
                "error_class",
                "error_detail",
                "updated_at",
            ]
        )

    logger.info(
        "Email verified attempt_id=%s user_id=%s",
        getattr(attempt, "pk", None),
        profile.user_id,
    )
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
        return redirect("customer_dashboard")

    try:
        send_verification_email(request, request.user)
    except Exception:
        logger.exception("Verification resend failed user_id=%s", request.user.pk)
        messages.error(
            request,
            "Die E-Mail konnte nicht versendet werden. Der Fehler wurde protokolliert. Bitte versuche es erneut oder kontaktiere das SAMS-Team.",
        )
    else:
        messages.success(request, "Ein neuer Bestätigungslink wurde an deine E-Mail-Adresse versendet.")
    return redirect("customer_dashboard")
