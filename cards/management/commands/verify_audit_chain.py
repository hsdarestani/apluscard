from django.core.management.base import BaseCommand, CommandError

from cards.models import Business
from cards.security_models import AuditChainSeal


class Command(BaseCommand):
    help = "Prüft die kryptografische Hash-Kette des Audit-Protokolls."

    def add_arguments(self, parser):
        parser.add_argument("--business", dest="business_slug", default="")

    def handle(self, *args, **options):
        businesses = Business.objects.all().order_by("pk")
        if options["business_slug"]:
            businesses = businesses.filter(slug=options["business_slug"])
        if not businesses.exists():
            raise CommandError("Kein passender Betrieb gefunden.")

        total = 0
        failures = []
        for business in businesses:
            previous_hash = ""
            expected_sequence = 1
            seals = (
                AuditChainSeal.objects.select_related("audit_event")
                .filter(business=business)
                .order_by("sequence")
            )
            audit_count = business.audit_events.count()
            seal_count = seals.count()
            if audit_count != seal_count:
                failures.append(
                    f"{business.slug}: {audit_count} Audit-Ereignisse, aber {seal_count} Siegel"
                )

            for seal in seals.iterator(chunk_size=500):
                event = seal.audit_event
                calculated = AuditChainSeal.calculate_hash(
                    event,
                    seal.sequence,
                    seal.previous_hash,
                )
                if seal.sequence != expected_sequence:
                    failures.append(
                        f"{business.slug}: Sequenz erwartet {expected_sequence}, gefunden {seal.sequence}"
                    )
                if seal.previous_hash != previous_hash:
                    failures.append(
                        f"{business.slug}: vorheriger Hash stimmt bei Sequenz {seal.sequence} nicht"
                    )
                if seal.event_hash != calculated:
                    failures.append(
                        f"{business.slug}: Ereignis-Hash stimmt bei Sequenz {seal.sequence} nicht"
                    )
                if event.business_id != business.pk:
                    failures.append(
                        f"{business.slug}: Ereignis {event.pk} gehört zu einem anderen Betrieb"
                    )
                previous_hash = seal.event_hash
                expected_sequence += 1
                total += 1

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(failure))
            raise CommandError(f"Audit-Integritätsprüfung fehlgeschlagen: {len(failures)} Fehler")

        self.stdout.write(self.style.SUCCESS(f"Audit-Kette ist gültig: {total} Ereignisse geprüft."))
