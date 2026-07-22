from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .experience_models import MemberNumberSequence
from .models import Wallet


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
