"""Owner notifications for completed member self-registrations."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from . import experience_services
from .models import AppNotification, Membership, Wallet


@receiver(post_save, sender=Wallet, dispatch_uid="sams_notify_owner_new_self_registration")
def notify_owner_new_self_registration(sender, instance, created, **kwargs):
    """Create an in-app + native push notification when a member signs up.

    The transient marker is set only by the public registration forms. This
    prevents imports, migrations, tests and staff-created cards from looking
    like customer self-registrations.
    """
    if not created or not instance.owner_id:
        return

    owner = instance.owner
    if not getattr(owner, "_sams_self_registration", False):
        return

    # Consume the marker so one request cannot notify twice accidentally.
    owner._sams_self_registration = False

    recipients = [
        membership.user
        for membership in Membership.objects.filter(
            business=instance.business,
            role=Membership.Role.OWNER,
            is_active=True,
            user__is_active=True,
        ).select_related("user")
    ]
    if not recipients:
        return

    experience_services.create_notifications(
        users=recipients,
        business=instance.business,
        kind=AppNotification.Kind.SYSTEM,
        title="Neues Mitglied registriert",
        body=f"{instance.display_name} · Mitgliedsnummer {instance.member_number}",
        data={
            "url": reverse("manager_wallet_detail", args=[instance.pk]),
            "wallet_id": str(instance.pk),
            "member_number": instance.member_number,
        },
    )
