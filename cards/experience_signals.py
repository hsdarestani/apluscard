from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .experience_models import LocationVisual, MemberNumberSequence
from .models import Location, Offer, Wallet


@receiver(post_save, sender=Wallet, dispatch_uid="cards.assign_sequential_member_number")
def assign_sequential_member_number(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return

    with transaction.atomic():
        sequence, _ = MemberNumberSequence.objects.select_for_update().get_or_create(
            pk=1,
            defaults={"next_number": 101},
        )
        number = sequence.next_number
        while Wallet.objects.exclude(pk=instance.pk).filter(member_number=str(number)).exists():
            number += 1

        Wallet.objects.filter(pk=instance.pk).update(member_number=str(number))
        sequence.next_number = number + 1
        sequence.save(update_fields=["next_number", "updated_at"])
        instance.member_number = str(number)


@receiver(post_save, sender=Location, dispatch_uid="cards.ensure_location_visual")
def ensure_location_visual(sender, instance, raw=False, **kwargs):
    if raw:
        return
    LocationVisual.objects.get_or_create(location=instance)


@receiver(post_save, sender=Offer, dispatch_uid="cards.notify_new_offer")
def notify_new_offer(sender, instance, created, raw=False, **kwargs):
    if raw or not created or not instance.is_active:
        return
    from .experience_services import notify_offer_audience
    transaction.on_commit(lambda: notify_offer_audience(instance))
