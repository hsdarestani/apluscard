from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from cards.management.commands.run_push_worker import claim_delivery, expire_stale_deliveries, process_delivery
from cards.models import AppNotification, Business
from cards.push_models import PushDelivery


class PushWorkerReliabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="push-reliability", password="secret")
        self.business = Business.objects.create(name="SAMS Push Reliability", slug="sams-push-reliability")
        self.notification = AppNotification.objects.create(
            recipient=self.user,
            business=self.business,
            kind=AppNotification.Kind.PAYMENT,
            title="A+ Pay Zahlung abgeschlossen",
            body="Testzustellung",
            data={"payment_request_id": "test"},
        )

    @override_settings(PUSH_MAX_ATTEMPTS=1, PUSH_NOTIFICATION_MAX_AGE_SECONDS=3600)
    @patch("cards.management.commands.run_push_worker.send_notification")
    def test_zero_provider_acceptance_is_never_marked_sent(self, mocked_send):
        mocked_send.return_value = {
            "device_count": 1,
            "sent_total": 0,
            "android": 0,
            "ios": 0,
            "errors": ["iOS Gerät 1: HTTP 400 BadDeviceToken"],
        }
        delivery = PushDelivery.objects.create(notification=self.notification, attempts=1)

        process_delivery(delivery)

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PushDelivery.Status.FAILED)
        self.assertEqual(delivery.sent_count, 0)
        self.assertIn("BadDeviceToken", delivery.last_error)

    @override_settings(PUSH_MAX_ATTEMPTS=5, PUSH_NOTIFICATION_MAX_AGE_SECONDS=3600)
    @patch("cards.management.commands.run_push_worker.send_notification")
    def test_zero_provider_acceptance_retries_before_max_attempts(self, mocked_send):
        mocked_send.return_value = {
            "device_count": 1,
            "sent_total": 0,
            "android": 0,
            "ios": 0,
            "errors": ["iOS Gerät 1: HTTP 503 ServiceUnavailable"],
        }
        delivery = PushDelivery.objects.create(notification=self.notification, attempts=1)

        process_delivery(delivery)

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PushDelivery.Status.RETRY)
        self.assertEqual(delivery.sent_count, 0)
        self.assertIsNone(delivery.processed_at)
        self.assertIn("ServiceUnavailable", delivery.last_error)

    @override_settings(PUSH_MAX_ATTEMPTS=5, PUSH_NOTIFICATION_MAX_AGE_SECONDS=3600)
    @patch("cards.management.commands.run_push_worker.send_notification")
    def test_partial_provider_acceptance_is_sent_without_duplicate_retry(self, mocked_send):
        mocked_send.return_value = {
            "device_count": 2,
            "sent_total": 1,
            "android": 0,
            "ios": 1,
            "errors": ["iOS Gerät 2: HTTP 410 Unregistered"],
        }
        delivery = PushDelivery.objects.create(notification=self.notification, attempts=1)

        process_delivery(delivery)

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PushDelivery.Status.SENT)
        self.assertEqual(delivery.sent_count, 1)
        self.assertIn("Teilzustellung", delivery.last_error)
        self.assertIn("Unregistered", delivery.last_error)

    @override_settings(PUSH_NOTIFICATION_MAX_AGE_SECONDS=3600)
    def test_stale_pending_deliveries_are_bulk_skipped(self):
        delivery = PushDelivery.objects.create(notification=self.notification)
        AppNotification.objects.filter(pk=self.notification.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )

        expired = expire_stale_deliveries()

        self.assertEqual(expired, 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PushDelivery.Status.SKIPPED)
        self.assertIsNotNone(delivery.processed_at)

    def test_freshest_due_delivery_is_claimed_first(self):
        older = AppNotification.objects.create(
            recipient=self.user,
            business=self.business,
            kind=AppNotification.Kind.SYSTEM,
            title="Older",
            body="Older queued push",
        )
        older_delivery = PushDelivery.objects.create(notification=older)
        fresh_delivery = PushDelivery.objects.create(notification=self.notification)
        AppNotification.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )

        claimed = claim_delivery()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, fresh_delivery.pk)
        older_delivery.refresh_from_db()
        self.assertEqual(older_delivery.status, PushDelivery.Status.PENDING)
