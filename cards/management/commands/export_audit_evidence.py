import json

from django.core.management.base import BaseCommand, CommandError

from cards.models import Business
from cards.security_models import AuditChainSeal


class Command(BaseCommand):
    help = "Exportiert das versiegelte Audit-Protokoll als kanonisches JSONL für externe Beweissicherung."

    def add_arguments(self, parser):
        parser.add_argument("--business", dest="business_slug", default="")

    def handle(self, *args, **options):
        businesses = Business.objects.all().order_by("pk")
        if options["business_slug"]:
            businesses = businesses.filter(slug=options["business_slug"])
        if not businesses.exists():
            raise CommandError("Kein passender Betrieb gefunden.")

        for business in businesses:
            seals = (
                AuditChainSeal.objects.select_related("audit_event", "audit_event__actor")
                .filter(business=business)
                .order_by("sequence")
            )
            for seal in seals.iterator(chunk_size=500):
                event = seal.audit_event
                self.stdout.write(
                    json.dumps(
                        {
                            "business": business.slug,
                            "sequence": seal.sequence,
                            "previous_hash": seal.previous_hash,
                            "event_hash": seal.event_hash,
                            "event": {
                                "id": event.pk,
                                "created_at": event.created_at.isoformat(),
                                "actor_id": event.actor_id,
                                "actor_username": event.actor.username if event.actor_id else None,
                                "action": event.action,
                                "object_type": event.object_type,
                                "object_id": event.object_id,
                                "details": event.details,
                                "ip_address": str(event.ip_address or ""),
                            },
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        default=str,
                    )
                )
