import hashlib
import json

from django.db import migrations


def backfill_audit_chain(apps, schema_editor):
    AuditEvent = apps.get_model("cards", "AuditEvent")
    AuditChainSeal = apps.get_model("cards", "AuditChainSeal")

    # Clear AuditEvent's Meta.ordering before DISTINCT. PostgreSQL otherwise
    # includes the ordering columns in the SELECT and can return the same
    # business_id more than once, causing the same chain to be backfilled twice.
    business_ids = (
        AuditEvent.objects.order_by()
        .values_list("business_id", flat=True)
        .distinct()
    )
    for business_id in business_ids.iterator(chunk_size=100):
        previous_hash = ""
        sequence = 0
        events = AuditEvent.objects.filter(business_id=business_id).order_by("created_at", "pk")
        for event in events.iterator(chunk_size=500):
            sequence += 1
            payload = json.dumps(
                {
                    "sequence": sequence,
                    "previous_hash": previous_hash,
                    "event_id": event.pk,
                    "business_id": event.business_id,
                    "actor_id": event.actor_id,
                    "action": event.action,
                    "object_type": event.object_type,
                    "object_id": event.object_id,
                    "details": event.details,
                    "ip_address": str(event.ip_address or ""),
                    "created_at": event.created_at.isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
            event_hash = hashlib.sha256(payload).hexdigest()
            AuditChainSeal.objects.create(
                audit_event_id=event.pk,
                business_id=business_id,
                sequence=sequence,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )
            previous_hash = event_hash


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0013_privileged_mfa_and_audit_chain"),
    ]

    operations = [
        migrations.RunPython(backfill_audit_chain, migrations.RunPython.noop),
    ]
