from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Sendet eine echte Testnachricht über die konfigurierte SMTP-Verbindung."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Empfänger der Testnachricht")

    def handle(self, *args, **options):
        if not settings.EMAIL_HOST:
            raise CommandError("EMAIL_HOST ist nicht konfiguriert.")
        if "smtp.EmailBackend" not in settings.EMAIL_BACKEND:
            raise CommandError("Der SMTP-Backend ist nicht aktiv.")
        recipient = options["to"].strip()
        timestamp = timezone.now().isoformat()
        message = EmailMultiAlternatives(
            subject=f"{settings.APP_NAME} SMTP-Test erfolgreich",
            body=(
                f"{settings.APP_NAME} konnte am {timestamp} erfolgreich eine E-Mail über den "
                f"Produktions-SMTP-Server versenden.\n\n{settings.APP_PUBLISHER}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            reply_to=[settings.EMAIL_REPLY_TO],
        )
        try:
            sent = message.send(fail_silently=False)
        except Exception as exc:
            raise CommandError(f"SMTP-Test fehlgeschlagen: {exc.__class__.__name__}: {exc}") from exc
        if sent != 1:
            raise CommandError("Der Mailserver hat die Testnachricht nicht angenommen.")
        self.stdout.write(self.style.SUCCESS(f"SMTP-Testnachricht wurde an {recipient} übergeben."))
