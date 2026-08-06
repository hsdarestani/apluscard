from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models import AuditEvent, Business
from .security_models import AuditChainSeal


@receiver(post_save, sender=AuditEvent, dispatch_uid="seal_audit_event_integrity")
def seal_audit_event(sender, instance, created, **kwargs):
    if not created or AuditChainSeal.objects.filter(audit_event=instance).exists():
        return

    # Lock the business row so concurrent audit events receive a deterministic,
    # gap-free sequence and cannot fork the hash chain.
    with transaction.atomic():
        Business.objects.select_for_update().get(pk=instance.business_id)
        previous = (
            AuditChainSeal.objects.filter(business_id=instance.business_id)
            .order_by("-sequence")
            .first()
        )
        sequence = 1 if previous is None else previous.sequence + 1
        previous_hash = "" if previous is None else previous.event_hash
        AuditChainSeal.objects.create(
            audit_event=instance,
            business_id=instance.business_id,
            sequence=sequence,
            previous_hash=previous_hash,
            event_hash=AuditChainSeal.calculate_hash(
                instance,
                sequence,
                previous_hash,
            ),
        )


@receiver(pre_delete, sender=AuditChainSeal, dispatch_uid="protect_audit_chain_seal_delete")
def protect_audit_chain_seal_delete(sender, instance, **kwargs):
    raise ProtectedError(
        "Audit-Integritätssiegel dürfen nicht gelöscht werden.",
        [instance],
    )
