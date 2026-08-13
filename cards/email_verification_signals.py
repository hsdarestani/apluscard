"""Keep django-allauth and SAMS member email verification aligned."""

import logging

from allauth.account.models import EmailAddress
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

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
    """Propagate SAMS verification to django-allauth."""
    sync_allauth_email_address(instance.user, verified=instance.email_verified)


@receiver(post_save, sender=EmailAddress, dispatch_uid="sams_sync_allauth_email_to_member")
def sync_allauth_email_to_member(sender, instance, **kwargs):
    """Propagate a verified allauth address back to the SAMS member profile.

    This also makes manual verification in Django admin immediately visible to
    the customer app. Verification is intentionally one-way: unchecking an
    allauth row must not silently revoke a member that was already verified.
    """
    if not instance.verified:
        return

    profile = MemberProfile.objects.filter(user_id=instance.user_id).first()
    if profile is None:
        return

    current_email = (profile.user.email or "").strip().lower()
    if current_email and current_email != (instance.email or "").strip().lower():
        return

    update_fields = []
    if not profile.email_verified:
        profile.email_verified = True
        update_fields.append("email_verified")
    if profile.email_verified_at is None:
        profile.email_verified_at = timezone.now()
        update_fields.append("email_verified_at")

    if update_fields:
        profile.save(update_fields=update_fields)
