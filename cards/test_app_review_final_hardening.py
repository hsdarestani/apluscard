import plistlib
from pathlib import Path
from unittest.mock import Mock, patch

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .account_deletion import complete_account_deletion
from .apple_credentials import revoke_apple_credentials, seal_apple_refresh_token
from .legal_models import AccountDeletionRequest, LegalConfiguration
from .models import Business, MemberProfile, PushDevice, Wallet


class IOSReviewBundleTests(TestCase):
    def test_privacy_manifest_is_valid_and_declares_no_tracking(self):
        manifest_path = Path(settings.BASE_DIR, "mobile", "ci", "PrivacyInfo.xcprivacy")
        with manifest_path.open("rb") as manifest_file:
            manifest = plistlib.load(manifest_file)
        self.assertFalse(manifest["NSPrivacyTracking"])
        self.assertEqual(manifest["NSPrivacyTrackingDomains"], [])
        declared_types = {
            item["NSPrivacyCollectedDataType"]
            for item in manifest["NSPrivacyCollectedDataTypes"]
        }
        self.assertIn("NSPrivacyCollectedDataTypeEmailAddress", declared_types)
        self.assertIn("NSPrivacyCollectedDataTypeDeviceID", declared_types)
        self.assertIn("NSPrivacyCollectedDataTypePurchaseHistory", declared_types)

    def test_ios_release_script_adds_camera_reason_and_final_bundle_gate(self):
        script = Path(settings.BASE_DIR, "mobile", "ci", "prepare-ios-release.rb").read_text(encoding="utf-8")
        self.assertIn("NSCameraUsageDescription", script)
        self.assertIn("PrivacyInfo.xcprivacy", script)
        self.assertIn("App Review compliance gate", script)
        self.assertIn("TARGET_BUILD_DIR", script)

    def test_qr_scanner_is_self_hosted_and_checksum_pinned(self):
        template = Path(settings.BASE_DIR, "cards", "templates", "cards", "manager_dashboard.html").read_text(encoding="utf-8")
        dockerfile = Path(settings.BASE_DIR, "Dockerfile").read_text(encoding="utf-8")
        middleware = Path(settings.BASE_DIR, "cards", "security_middleware.py").read_text(encoding="utf-8")
        self.assertIn("cards/vendor/html5-qrcode.min.js", template)
        self.assertNotIn("unpkg.com", template)
        self.assertIn("html5-qrcode/2.3.8", dockerfile)
        self.assertIn("sha512sum --check --strict", dockerfile)
        self.assertNotIn("unpkg.com", middleware)


@override_settings(
    APPLE_KEY_ID="APPLEKEY",
    APPLE_TEAM_ID="APPLETEAM",
    APPLE_PRIVATE_KEY="test-private-key",
    APPLE_BUNDLE_ID="de.aplussolution.samscard",
    IOS_BUNDLE_ID="de.aplussolution.samscard",
)
class AppleCredentialRevocationTests(TestCase):
    def test_refresh_token_is_encrypted_and_revoked(self):
        user = get_user_model().objects.create_user(username="apple-delete", email="apple-delete@example.com")
        encrypted = seal_apple_refresh_token("private-refresh-token")
        self.assertNotIn("private-refresh-token", encrypted)
        account = SocialAccount.objects.create(
            user=user,
            provider="apple",
            uid="apple-delete-uid",
            extra_data={
                "refresh_token_encrypted": encrypted,
                "refresh_token_client_id": "de.aplussolution.samscard",
            },
        )
        response = Mock()
        response.raise_for_status.return_value = None
        with patch("cards.apple_credentials._client_secret", return_value="signed-secret"), patch(
            "cards.apple_credentials.httpx.post",
            return_value=response,
        ) as post:
            status = revoke_apple_credentials(user)

        self.assertEqual(status, "revoked")
        self.assertEqual(post.call_args.kwargs["data"]["token"], "private-refresh-token")
        account.refresh_from_db()
        self.assertNotIn("refresh_token_encrypted", account.extra_data)
        self.assertNotIn("refresh_token_client_id", account.extra_data)


@override_settings(
    DEFAULT_BUSINESS_SLUG="shisha-bar",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Sams Club Lounge <app@example.com>",
    EMAIL_REPLY_TO="support@example.com",
)
class AccountDeletionReviewTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Sams Club Lounge", slug="shisha-bar")
        LegalConfiguration.objects.create(
            business=self.business,
            app_display_name="Sams Club Lounge",
            controller_name="A+ Solution GmbH",
            controller_address="Musterstraße 1, 60311 Frankfurt",
            contact_email="app@example.com",
            privacy_email="privacy@example.com",
        )
        self.user = get_user_model().objects.create_user(
            username="delete-member@example.com",
            email="delete-member@example.com",
            password="Deletion-Test-2026!",
            first_name="Delete",
            last_name="Member",
        )
        MemberProfile.objects.create(user=self.user, age_confirmed=True, email_verified=True)
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.user,
            display_name="Delete Member",
            phone="+49 160 1234567",
            email=self.user.email,
        )
        PushDevice.objects.create(user=self.user, platform=PushDevice.Platform.IOS, token="delete-device-token")

    def test_logged_in_customer_can_start_deletion_inside_the_app(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("app_account_deletion", args=[self.business.slug]),
            {"confirmation": "on", "confirmation_text": "LÖSCHEN"},
        )

        self.assertEqual(response.status_code, 200)
        deletion_request = AccountDeletionRequest.objects.get(user=self.user)
        self.assertEqual(deletion_request.status, AccountDeletionRequest.Status.PROCESSING)
        self.assertContains(response, "7 Kalendertagen")
        self.assertContains(response, deletion_request.reference_number)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("7 Kalendertagen", mail.outbox[0].body)

    def test_completion_removes_direct_identifiers_and_sends_confirmation(self):
        deletion_request = AccountDeletionRequest.objects.create(
            business=self.business,
            user=self.user,
            wallet=self.wallet,
            email=self.user.email,
            member_number=self.wallet.member_number,
            status=AccountDeletionRequest.Status.PROCESSING,
        )

        with patch("cards.account_deletion.revoke_apple_credentials", return_value="revoked"):
            with self.captureOnCommitCallbacks(execute=True):
                result = complete_account_deletion(deletion_request)

        self.assertEqual(result["status"], "deleted")
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.wallet.refresh_from_db()
        self.assertIsNone(self.wallet.owner)
        self.assertEqual(self.wallet.phone, "")
        self.assertEqual(self.wallet.email, "")
        self.assertEqual(self.wallet.status, Wallet.Status.CLOSED)
        self.assertTrue(self.wallet.display_name.startswith("Gelöschtes Mitglied"))
        deletion_request.refresh_from_db()
        self.assertEqual(deletion_request.status, AccountDeletionRequest.Status.COMPLETED)
        self.assertEqual(deletion_request.member_number, "")
        self.assertTrue(deletion_request.email.endswith("@example.invalid"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Kontolöschung abgeschlossen", mail.outbox[0].subject)

    def test_legal_pages_disclose_optional_fields_and_seven_day_deletion(self):
        privacy = self.client.get(reverse("app_privacy_policy", args=[self.business.slug]))
        terms = self.client.get(reverse("app_terms", args=[self.business.slug]))
        deletion = self.client.get(reverse("app_account_deletion", args=[self.business.slug]))
        self.assertContains(privacy, "Freiwillige Profilangaben")
        self.assertContains(privacy, "sieben Kalendertagen")
        self.assertContains(terms, "Mobilnummer und Geburtsdatum sind freiwillige Profilangaben")
        self.assertContains(deletion, "7 Kalendertagen")
