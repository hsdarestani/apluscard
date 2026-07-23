import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.html import escape

logger = logging.getLogger(__name__)


def send_verification_email(request, user):
    from .views import _verification_token

    token = _verification_token(user)
    url = request.build_absolute_uri(reverse("verify_email", args=[token]))
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
      <div style="font-size:28px;font-weight:900;letter-spacing:-1px;margin-bottom:22px">A+</div>
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
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
        reply_to=[settings.EMAIL_REPLY_TO],
    )
    message.attach_alternative(html_body, "text/html")
    sent = message.send(fail_silently=False)
    if sent != 1:
        raise RuntimeError("Der Mailserver hat die Bestätigungsnachricht nicht angenommen.")
    logger.info("Verification email accepted for user_id=%s", user.pk)
    return True
