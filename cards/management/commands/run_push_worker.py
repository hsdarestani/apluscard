import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from cards.models import AppNotification
from cards.push_models import PushDelivery
from cards.push_services import send_notification

logger = logging.getLogger(__name__)


def enqueue_recent_notifications(limit=500):
    cutoff = timezone.now() - timedelta(seconds=settings.PUSH_NOTIFICATION_MAX_AGE_SECONDS)
    notification_ids = list(
        AppNotification.objects.filter(created_at__gte=cutoff, push_delivery__isnull=True)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    if notification_ids:
        PushDelivery.objects.bulk_create(
            [PushDelivery(notification_id=notification_id) for notification_id in notification_ids],
            ignore_conflicts=True,
        )
    return len(notification_ids)


def claim_delivery():
    now = timezone.now()
    stale_before = now - timedelta(minutes=10)
    PushDelivery.objects.filter(
        status=PushDelivery.Status.PROCESSING,
        updated_at__lt=stale_before,
    ).update(
        status=PushDelivery.Status.RETRY,
        next_attempt_at=now,
        last_error="Verwaisten Processing-Status automatisch zurückgesetzt.",
    )
    with transaction.atomic():
        delivery = (
            PushDelivery.objects.select_for_update(skip_locked=True)
            .select_related("notification", "notification__recipient", "notification__business", "notification__location")
            .filter(
                status__in=[PushDelivery.Status.PENDING, PushDelivery.Status.RETRY],
                next_attempt_at__lte=now,
            )
            .order_by("next_attempt_at", "created_at")
            .first()
        )
        if not delivery:
            return None
        delivery.status = PushDelivery.Status.PROCESSING
        delivery.attempts = F("attempts") + 1
        delivery.last_error = ""
        delivery.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        delivery.refresh_from_db(fields=["attempts"])
        return delivery


def process_delivery(delivery):
    now = timezone.now()
    max_age = timedelta(seconds=settings.PUSH_NOTIFICATION_MAX_AGE_SECONDS)
    if now - delivery.notification.created_at > max_age:
        delivery.status = PushDelivery.Status.SKIPPED
        delivery.last_error = "Mitteilung ist für Push zu alt."
        delivery.processed_at = now
        delivery.save(update_fields=["status", "last_error", "processed_at", "updated_at"])
        return

    result = send_notification(delivery.notification)
    device_count = result["device_count"]
    sent_count = result["sent_total"]
    errors = result["errors"]

    delivery.sent_count = sent_count
    delivery.processed_at = now
    if device_count == 0:
        delivery.status = PushDelivery.Status.SKIPPED
        delivery.last_error = "Kein aktives iOS- oder Android-Gerät registriert."
    elif errors and delivery.attempts < settings.PUSH_MAX_ATTEMPTS:
        delivery.status = PushDelivery.Status.RETRY
        delay_minutes = min(60, 2 ** max(delivery.attempts - 1, 0))
        delivery.next_attempt_at = now + timedelta(minutes=delay_minutes)
        delivery.last_error = " | ".join(errors)[:4000]
        delivery.processed_at = None
    elif errors:
        delivery.status = PushDelivery.Status.FAILED
        delivery.last_error = " | ".join(errors)[:4000]
    else:
        delivery.status = PushDelivery.Status.SENT
        delivery.last_error = ""
    delivery.save(
        update_fields=["status", "sent_count", "next_attempt_at", "last_error", "processed_at", "updated_at"]
    )


class Command(BaseCommand):
    help = "Sendet ausstehende native Push-Mitteilungen über FCM und APNs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Nur einen Durchlauf ausführen.")
        parser.add_argument("--poll", type=float, default=3.0, help="Wartezeit zwischen Durchläufen.")

    def handle(self, *args, **options):
        once = options["once"]
        poll = max(1.0, options["poll"])
        self.stdout.write("SAMS Push Worker gestartet.")
        while True:
            if not settings.PUSH_NOTIFICATIONS_ENABLED:
                if once:
                    self.stdout.write("Push ist deaktiviert; kein Versand.")
                    return
                time.sleep(max(poll, 10))
                continue

            enqueue_recent_notifications()
            processed = 0
            while processed < 100:
                delivery = claim_delivery()
                if delivery is None:
                    break
                try:
                    process_delivery(delivery)
                except Exception as exc:
                    logger.exception("Push delivery %s failed.", delivery.pk)
                    delivery.status = PushDelivery.Status.RETRY if delivery.attempts < settings.PUSH_MAX_ATTEMPTS else PushDelivery.Status.FAILED
                    delivery.next_attempt_at = timezone.now() + timedelta(minutes=5)
                    delivery.last_error = str(exc)[:4000]
                    delivery.processed_at = None
                    delivery.save(update_fields=["status", "next_attempt_at", "last_error", "processed_at", "updated_at"])
                processed += 1

            if once:
                self.stdout.write(f"{processed} Push-Aufträge verarbeitet.")
                return
            time.sleep(poll)
