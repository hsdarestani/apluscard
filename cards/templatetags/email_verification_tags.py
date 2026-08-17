from django import template

from cards.email_verification_models import EmailVerificationAttempt


register = template.Library()


@register.simple_tag
def latest_email_verification_attempt(user):
    if user is None or not getattr(user, "pk", None):
        return None
    return (
        EmailVerificationAttempt.objects.filter(user=user)
        .order_by("-created_at")
        .first()
    )
