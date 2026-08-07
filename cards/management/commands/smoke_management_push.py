from django.core.management.base import BaseCommand, CommandError

from cards.models import AppNotification, Membership, PushDevice
from cards.push_services import send_notification


class Command(BaseCommand):
    help = "Sendet genau eine echte Push-Testnachricht an ein registriertes internes SAMS-Gerät."

    def handle(self, *args, **options):
        membership = (
            Membership.objects.filter(
                is_active=True,
                role__in=[Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.STAFF],
                user__push_devices__is_active=True,
                user__push_devices__platform__in=[PushDevice.Platform.ANDROID, PushDevice.Platform.IOS],
            )
            .select_related("user", "business")
            .distinct()
            .order_by("role", "created_at")
            .first()
        )
        if membership is None:
            raise CommandError("Kein internes iOS- oder Android-Gerät für einen echten Push-Smoke-Test registriert.")

        notification = AppNotification.objects.create(
            recipient=membership.user,
            business=membership.business,
            kind=AppNotification.Kind.SYSTEM,
            title="SAMS Push-Test erfolgreich",
            body="Die Push-Verbindung zum neuen SAMS-Server wurde erfolgreich geprüft.",
            data={"url": "/mitteilungen/", "production_smoke_test": True},
        )
        result = send_notification(notification)
        if result["device_count"] == 0 or result["sent_total"] == 0:
            detail = " | ".join(result["errors"]) or "Kein Push wurde vom Provider angenommen."
            raise CommandError(detail)

        self.stdout.write(
            self.style.SUCCESS(
                "Production Push Smoke OK · "
                f"Geräte={result['device_count']} · gesendet={result['sent_total']} · "
                f"Android={result['android']} · iOS={result['ios']}"
            )
        )
        if result["errors"]:
            self.stdout.write(self.style.WARNING("Teilfehler: " + " | ".join(result["errors"])))
