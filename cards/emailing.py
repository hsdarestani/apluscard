import hashlib
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .email_verification_models import EmailVerificationAttempt

logger = logging.getLogger(__name__)


def verification_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _trigger_for_request(request):
    path = getattr(request, "path", "") or ""
    if "resend-verification" in path:
        return EmailVerificationAttempt.Trigger.RESEND
    if "register" in path:
        return EmailVerificationAttempt.Trigger.REGISTRATION
    return EmailVerificationAttempt.Trigger.OTHER


def _verification_url(request, token):
    path = reverse("verify_email", args=[token])
    public_base_url = getattr(settings, "APP_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url:
        return f"{public_base_url}{path}"
    return request.build_absolute_uri(path)


def send_verification_email(request, user):
    # Keep the token format compatible with verification links that were already
    # issued before delivery auditing was added.
    from .views import _verification_token

    token = _verification_token(user)
    url = _verification_url(request, token)
    wallet = user.wallets.select_related("business").first()
    partner_name = wallet.business.name if wallet else "deinen A+ Partner"
    display_name = user.first_name or "A+ Member"
    subject = f"{settings.APP_NAME} – E-Mail-Adresse bestätigen"
    text_body = (
        f"Hallo {display_name},\n\n"
        f"bitte bestätige deine E-Mail-Adresse für deine digitale Mitgliedskarte bei {partner_name}:\n"
        f"{url}\n\n"
        "Der Link ist 48 Stunden gültig.\n\n"
        f"{settings.APP_NAME}\n"
        f"{settings.APP_PUBLISHER}"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#17121d">
      <div style="font-size:25px;font-weight:900;letter-spacing:-1px;margin-bottom:22px;color:#7c3cff">{escape(settings.APP_NAME)}</div>
      <h1 style="font-size:24px">E-Mail-Adresse bestätigen</h1>
      <p>Hallo {escape(display_name)},</p>
      <p>bestätige bitte deine E-Mail-Adresse, damit deine digitale Mitgliedskarte bei <strong>{escape(partner_name)}</strong> vollständig freigeschaltet wird.</p>
      <p style="margin:28px 0">
        <a href="{escape(url)}" style="display:inline-block;padding:14px 22px;border-radius:12px;background:#8b35ff;color:#fff;text-decoration:none;font-weight:700">E-Mail-Adresse bestätigen</a>
      </p>
      <p style="font-size:13px;color:#665d6c">Der Link ist 48 Stunden gültig. Falls du dich nicht registriert hast, kannst du diese Nachricht ignorieren.</p>
      <p style="font-size:13px;color:#665d6c"><strong>{escape(settings.APP_NAME)}</strong> · {escape(settings.APP_PUBLISHER)}</p>
    </div>
    """

    attempt = EmailVerificationAttempt.objects.create(
        user=user,
        email=(user.email or "").strip().lower(),
        trigger=_trigger_for_request(request),
        status=EmailVerificationAttempt.Status.PENDING,
        token_hash=verification_token_hash(token),
        backend=settings.EMAIL_BACKEND[:255],
        request_host=request.get_host()[:255],
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
        reply_to=[settings.EMAIL_REPLY_TO],
    )
    message.attach_alternative(html_body, "text/html")

    try:
        sent = message.send(fail_silently=False)
        if sent != 1:
            raise RuntimeError("Der Mailserver hat die Bestätigungsnachricht nicht angenommen.")
    except Exception as exc:
        attempt.status = EmailVerificationAttempt.Status.FAILED
        attempt.error_class = exc.__class__.__name__[:120]
        attempt.error_detail = str(exc)[:4000]
        attempt.save(update_fields=["status", "error_class", "error_detail", "updated_at"])
        logger.exception(
            "Verification email failed attempt_id=%s user_id=%s",
            attempt.pk,
            user.pk,
        )
        raise

    attempt.status = EmailVerificationAttempt.Status.ACCEPTED
    attempt.accepted_at = timezone.now()
    attempt.error_class = ""
    attempt.error_detail = ""
    attempt.save(
        update_fields=[
            "status",
            "accepted_at",
            "error_class",
            "error_detail",
            "updated_at",
        ]
    )
    logger.info(
        "Verification email accepted attempt_id=%s user_id=%s",
        attempt.pk,
        user.pk,
    )
    return True
