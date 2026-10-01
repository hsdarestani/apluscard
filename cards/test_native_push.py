import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .management.commands.run_push_worker import enqueue_recent_notifications
from .models import AppNotification, Business, PushDevice, Wallet
from .push_models import PushDelivery
from .push_services import send_notification, sync_user_badge
from .wallet_pass import _pass_files


class NativePushRegistrationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="member-one", password="secret")
        self.other_user = user_model.objects.create_user(username="member-two", password="secret")

    def test_authenticated_app_can_register_and_disable_device(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_push_devices"),
            data=json.dumps({"platform": "ANDROID", "token": "android-token-123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        device = PushDevice.objects.get(token="android-token-123")
        self.assertEqual(device.user, self.user)
        self.assertTrue(device.is_active)

        response = self.client.delete(
            reverse("api_push_devices"),
            data=json.dumps({"token": "android-token-123"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 204)
        device.refresh_from_db()
        self.assertFalse(device.is_active)

    def test_same_native_token_moves_to_current_account(self):
        PushDevice.objects.create(user=self.user, platform=PushDevice.Platform.IOS, token="shared-ios-token")
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse("api_push_devices"),
            data=json.dumps({"platform": "IOS", "token": "shared-ios-token"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        device = PushDevice.objects.get(token="shared-ios-token")
        self.assertEqual(device.user, self.other_user)
        self.assertTrue(device.is_active)


class NativePushDeliveryTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="push-member", password="secret")
        self.business = Business.objects.create(name="SAMS Club Lounge", slug="sams")
        self.notification = AppNotification.objects.create(
            recipient=self.user,
            business=self.business,
            kind=AppNotification.Kind.SYSTEM,
            title="SAMS Nachricht",
            body="Eine wichtige Mitteilung.",
            data={"url": "/mitteilungen/"},
        )

    def test_worker_enqueues_each_notification_once(self):
        self.assertEqual(enqueue_recent_notifications(), 1)
        delivery = PushDelivery.objects.get(notification=self.notification)
        self.assertEqual(delivery.status, PushDelivery.Status.PENDING)
        self.assertEqual(enqueue_recent_notifications(), 0)
        self.assertEqual(PushDelivery.objects.count(), 1)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    def test_notification_without_registered_device_is_safe(self):
        result = send_notification(self.notification)
        self.assertEqual(result["device_count"], 0)
        self.assertEqual(result["sent_total"], 0)
        self.assertEqual(result["errors"], [])

    @override_settings(
        PUSH_NOTIFICATIONS_ENABLED=True,
        APNS_PRIVATE_KEY_BASE64="",
        APNS_KEY_ID="",
        APNS_TEAM_ID="",
        IOS_BUNDLE_ID="de.aplussolution.samscard",
    )
    def test_ios_configuration_error_is_reported_for_retry(self):
        PushDevice.objects.create(user=self.user, platform=PushDevice.Platform.IOS, token="ios-device-token")
        result = send_notification(self.notification)
        self.assertEqual(result["device_count"], 1)
        self.assertEqual(result["sent_total"], 0)
        self.assertTrue(any(error.startswith("iOS:") for error in result["errors"]))


class SamsWalletDesignTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="wallet-member", password="secret")
        self.business = Business.objects.create(name="SAMS Club Lounge", slug="sams-wallet")
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.user,
            display_name="Ashkan Dian",
        )

    @override_settings(
        APP_NAME="Sams Club Lounge",
        APP_PUBLISHER="A+ Solution GmbH",
        APP_SUPPORT_EMAIL="app@aplus-solution.de",
        APPLE_WALLET_PASS_TYPE_ID="pass.de.sams.member",
        APPLE_WALLET_TEAM_ID="TEAM123456",
    )
    def test_wallet_has_clean_layout_and_no_oversized_member_number(self):
        request = RequestFactory().get(
            "/customer/apple-wallet/",
            HTTP_HOST="app.samsclublounge.de",
            secure=True,
        )
        files = _pass_files(self.wallet, request)
        payload = json.loads(files["pass.json"])
        barcode = payload["barcodes"][0]
        store_card = payload["storeCard"]

        self.assertNotIn("logoText", payload)
        self.assertNotIn("primaryFields", store_card)
        self.assertEqual(store_card["headerFields"][0]["value"], self.wallet.member_number)
        self.assertEqual(store_card["secondaryFields"][0]["value"], "Ashkan Dian")
        self.assertNotIn("altText", barcode)
        self.assertIn("strip.png", files)
        self.assertIn("strip@2x.png", files)
        self.assertNotIn("thumbnail.png", files)
        self.assertGreater(len(files["strip@2x.png"]), 1000)


class NotificationBadgeSyncTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="badge-member", password="secret")
        self.business = Business.objects.create(name="Badge Business", slug="badge-business")
        self.notification = AppNotification.objects.create(
            recipient=self.user,
            business=self.business,
            kind=AppNotification.Kind.SYSTEM,
            title="Badge Test",
            body="Bitte lesen.",
        )
        self.client.force_login(self.user)

    @patch("cards.experience_views.sync_user_badge")
    def test_web_read_syncs_native_badge(self, sync_badge):
        response = self.client.post(reverse("notification_read", args=[self.notification.pk]))
        self.assertEqual(response.status_code, 302)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
        sync_badge.assert_called_once()
        self.assertEqual(sync_badge.call_args.args[0].pk, self.user.pk)

    @patch("cards.experience_views.sync_user_badge")
    def test_read_all_syncs_native_badge(self, sync_badge):
        AppNotification.objects.create(
            recipient=self.user,
            business=self.business,
            kind=AppNotification.Kind.SYSTEM,
            title="Noch eine",
            body="Auch lesen.",
        )
        response = self.client.post(reverse("notifications_read_all"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.user.app_notifications.filter(is_read=False).exists())
        sync_badge.assert_called_once()

    @patch("cards.api.sync_user_badge")
    def test_api_read_syncs_native_badge(self, sync_badge):
        response = self.client.post(
            reverse("api_notifications"),
            data=json.dumps({"id": self.notification.pk}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
        sync_badge.assert_called_once()

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=False)
    def test_badge_sync_is_safe_without_push_runtime(self):
        result = sync_user_badge(self.user)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["ios"], 0)
        self.assertEqual(result["errors"], [])
