"""Keep django-allauth EmailAddress rows aligned with SAMS member verification."""

import logging

from allauth.account.models import EmailAddress
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MemberProfile

logger = logging.getLogger(__name__)


def sync_allauth_email_address(user, *, verified):
    """Ensure the user's current email exists in allauth and never loses verification."""
    email = (user.email or "").strip()
    if not email:
        return None

    address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if address is None:
        conflict = EmailAddress.objects.filter(email__iexact=email).exclude(user=user).first()
        if conflict is not None:
            logger.warning(
                "Cannot sync allauth email for user_id=%s: email already belongs to user_id=%s",
                user.pk,
                conflict.user_id,
            )
            return None

        has_primary = EmailAddress.objects.filter(user=user, primary=True).exists()
        return EmailAddress.objects.create(
            user=user,
            email=email,
            verified=bool(verified),
            primary=not has_primary,
        )

    update_fields = []
    if verified and not address.verified:
        address.verified = True
        update_fields.append("verified")

    if not EmailAddress.objects.filter(user=user, primary=True).exists() and not address.primary:
        address.primary = True
        update_fields.append("primary")

    if update_fields:
        address.save(update_fields=update_fields)
    return address


@receiver(post_save, sender=MemberProfile, dispatch_uid="sams_sync_member_email_to_allauth")
def sync_member_email_to_allauth(sender, instance, **kwargs):
    sync_allauth_email_address(instance.user, verified=instance.email_verified)
