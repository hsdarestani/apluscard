import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .management.commands.run_push_worker import enqueue_recent_notifications
from .models import AppNotification, Business, PushDevice, Wallet
from .push_models import PushDelivery
from .push_services import send_notification
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
        APP_NAME="SAMS Card",
        APP_PUBLISHER="A+ Solution GmbH",
        APP_SUPPORT_EMAIL="app@aplus-solution.de",
        APPLE_WALLET_PASS_TYPE_ID="pass.de.sams.member",
        APPLE_WALLET_TEAM_ID="TEAM123456",
    )
    def test_wallet_has_premium_assets_and_no_member_caption_below_qr(self):
        request = RequestFactory().get(
            "/customer/apple-wallet/",
            HTTP_HOST="cards.smarbiz.sbs",
            secure=True,
        )
        files = _pass_files(self.wallet, request)
        payload = json.loads(files["pass.json"])
        barcode = payload["barcodes"][0]

        self.assertEqual(payload["logoText"], "SAMS")
        self.assertNotIn("altText", barcode)
        self.assertIn("strip.png", files)
        self.assertIn("strip@2x.png", files)
        self.assertIn("thumbnail.png", files)
        self.assertGreater(len(files["strip@2x.png"]), 1000)
