from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cards.models import AuditEvent, Membership
from cards.security_models import PrivilegedMfaDevice


class Command(BaseCommand):
    help = "Setzt 2FA für ein privilegiertes Konto im dokumentierten Notfallprozess zurück."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--business", dest="business_slug", default="")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--confirm", required=True)

    def handle(self, *args, **options):
        if options["confirm"] != "RESET-2FA":
            raise CommandError("Zur Bestätigung muss --confirm RESET-2FA angegeben werden.")
        if len(options["reason"].strip()) < 10:
            raise CommandError("Der dokumentierte Grund muss mindestens 10 Zeichen enthalten.")

        User = get_user_model()
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("Benutzer wurde nicht gefunden.") from exc

        memberships = Membership.objects.select_related("business").filter(
            user=user,
            is_active=True,
            role__in=[Membership.Role.OWNER, Membership.Role.MANAGER],
        )
        if options["business_slug"]:
            memberships = memberships.filter(business__slug=options["business_slug"])
        membership = memberships.first()
        if membership is None:
            raise CommandError("Für dieses Konto wurde keine aktive Inhaber-/Leitungsrolle gefunden.")

        deleted, _ = PrivilegedMfaDevice.objects.filter(user=user).delete()
        AuditEvent.objects.create(
            actor=None,
            business=membership.business,
            action="mfa_emergency_reset",
            object_type="user",
            object_id=str(user.pk),
            details={
                "username": user.username,
                "reason": options["reason"].strip(),
                "device_deleted": bool(deleted),
                "source": "management_command",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                "2FA wurde zurückgesetzt. Beim nächsten privilegierten Zugriff ist eine Neueinrichtung erforderlich."
            )
        )
