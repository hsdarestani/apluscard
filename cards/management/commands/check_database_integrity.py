from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import F

from cards.models import (
    AppNotification,
    Business,
    LedgerEntry,
    Membership,
    PaymentRequest,
    PushDevice,
    Wallet,
)
from cards.push_models import PushDelivery


class Command(BaseCommand):
    help = "Prüft, dass Production ausschließlich die kanonische PostgreSQL-Datenbank nutzt und Kernrelationen konsistent sind."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-non-postgres",
            action="store_true",
            help="Nur für lokale Entwicklung/Tests: andere Datenbanken zulassen.",
        )

    def handle(self, *args, **options):
        allow_non_postgres = options["allow_non_postgres"]
        if connection.vendor != "postgresql" and not allow_non_postgres:
            raise CommandError(
                f"Production muss PostgreSQL verwenden; aktuell ist {connection.vendor!r} aktiv."
            )

        database_name = connection.settings_dict.get("NAME") or "?"
        sqlite_path = Path(settings.BASE_DIR) / "db.sqlite3"
        if connection.vendor == "postgresql" and sqlite_path.exists() and sqlite_path.stat().st_size > 0:
            raise CommandError(
                f"Neben der kanonischen PostgreSQL-Datenbank wurde eine lokale SQLite-Datei gefunden: {sqlite_path}. "
                "Sie darf in Production nicht als zweite Datenquelle bestehen."
            )

        checks = {
            "payment_business_vs_wallet": PaymentRequest.objects.exclude(
                business_id=F("wallet__business_id")
            ).count(),
            "payment_business_vs_location": PaymentRequest.objects.exclude(
                business_id=F("location__business_id")
            ).count(),
            "ledger_business_vs_wallet": LedgerEntry.objects.exclude(
                business_id=F("wallet__business_id")
            ).count(),
            "notification_business_vs_location": AppNotification.objects.filter(
                location__isnull=False
            ).exclude(business_id=F("location__business_id")).count(),
        }
        broken = {name: count for name, count in checks.items() if count}
        if broken:
            detail = ", ".join(f"{name}={count}" for name, count in broken.items())
            raise CommandError(f"Datenintegritätsfehler gefunden: {detail}")

        counts = {
            "businesses": Business.objects.count(),
            "memberships": Membership.objects.count(),
            "wallets": Wallet.objects.count(),
            "payments": PaymentRequest.objects.count(),
            "ledger_entries": LedgerEntry.objects.count(),
            "notifications": AppNotification.objects.count(),
            "push_devices": PushDevice.objects.count(),
            "push_deliveries": PushDelivery.objects.count(),
        }
        snapshot = " · ".join(f"{key}={value}" for key, value in counts.items())
        self.stdout.write(
            self.style.SUCCESS(
                f"Canonical database OK · vendor={connection.vendor} · name={database_name} · {snapshot}"
            )
        )
