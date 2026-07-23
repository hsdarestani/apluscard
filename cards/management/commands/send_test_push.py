from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cards.models import AppNotification, Membership, Wallet
from cards.push_services import send_notification


class Command(BaseCommand):
    help = "Sendet eine echte Test-Push-Mitteilung an alle aktiven Geräte eines Benutzers."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--title", default="SAMS Push funktioniert")
        parser.add_argument(
            "--body",
            default="Diese Test-Mitteilung wurde sicher vom SAMS Server an dein Gerät gesendet.",
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"])
        except user_model.DoesNotExist as exc:
            raise CommandError("Benutzer nicht gefunden.") from exc

        wallet = Wallet.objects.filter(owner=user).select_related("business").first()
        membership = Membership.objects.filter(user=user, is_active=True).select_related("business").first()
        business = wallet.business if wallet else (membership.business if membership else None)
        if business is None:
            raise CommandError("Der Benutzer gehört zu keinem SAMS Betrieb.")

        notification = AppNotification.objects.create(
            recipient=user,
            business=business,
            kind=AppNotification.Kind.SYSTEM,
            title=options["title"],
            body=options["body"],
            data={"url": "/mitteilungen/", "test": True},
        )
        result = send_notification(notification)
        self.stdout.write(
            self.style.SUCCESS(
                f"Geräte: {result['device_count']} · gesendet: {result['sent_total']} "
                f"(Android {result['android']}, iOS {result['ios']})"
            )
        )
        if result["errors"]:
            raise CommandError(" | ".join(result["errors"]))
