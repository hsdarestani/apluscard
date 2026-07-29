import json
from pathlib import Path
from unittest.mock import patch

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


APPLE_UID = "001234.abcdef1234567890.1234"
APPLE_EMAIL = "member@privaterelay.appleid.com"
NONCE = "nonce-for-native-apple-login"


@override_settings(
    APPLE_BUNDLE_ID="de.aplussolution.samscard",
    IOS_BUNDLE_ID="de.aplussolution.samscard",
    APPLE_KEY_ID="TESTKEY123",
    APPLE_TEAM_ID="VHB87QGU46",
    APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
)
class NativeAppleLoginTests(TestCase):
    def payload(self, **overrides):
        payload = {
            "authorizationCode": "single-use-code",
            "idToken": "native-id-token",
            "user": APPLE_UID,
            "email": APPLE_EMAIL,
            "givenName": "Sams",
            "familyName": "Member",
            "realUserStatus": 2,
            "nonce": NONCE,
        }
        payload.update(overrides)
        return payload

    def claims(self, **overrides):
        claims = {
            "sub": APPLE_UID,
            "email": APPLE_EMAIL,
            "email_verified": True,
            "nonce": NONCE,
            "is_private_email": True,
        }
        claims.update(overrides)
        return claims

    def post(self, payload=None):
        return self.client.post(
            reverse("native_apple_login"),
            data=json.dumps(payload or self.payload()),
            content_type="application/json",
        )

    @patch("cards.apple_views._decode_apple_identity_token")
    @patch("cards.apple_views._exchange_apple_code")
    def test_verified_native_credential_creates_session_and_social_account(self, exchange, decode):
        exchange.return_value = {"id_token": "server-id-token"}
        decode.return_value = self.claims()

        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect"], reverse("complete_customer_profile"))
        user = get_user_model().objects.get(email=APPLE_EMAIL)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        social = SocialAccount.objects.get(provider="apple", uid=APPLE_UID)
        self.assertEqual(social.user, user)
        exchange.assert_called_once_with("single-use-code", "de.aplussolution.samscard")
        decode.assert_called_once_with("server-id-token", "de.aplussolution.samscard")

    @patch("cards.apple_views._decode_apple_identity_token")
    @patch("cards.apple_views._exchange_apple_code")
    def test_existing_apple_identity_is_reused(self, exchange, decode):
        User = get_user_model()
        existing_user = User.objects.create_user(username="existing-apple", email=APPLE_EMAIL)
        SocialAccount.objects.create(user=existing_user, provider="apple", uid=APPLE_UID, extra_data={})
        exchange.return_value = {"id_token": "server-id-token"}
        decode.return_value = self.claims()

        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.filter(email=APPLE_EMAIL).count(), 1)
        self.assertEqual(SocialAccount.objects.filter(provider="apple", uid=APPLE_UID).count(), 1)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(existing_user.pk))

    @patch("cards.apple_views._decode_apple_identity_token")
    @patch("cards.apple_views._exchange_apple_code")
    def test_native_user_must_match_verified_token_subject(self, exchange, decode):
        exchange.return_value = {"id_token": "server-id-token"}
        decode.return_value = self.claims(sub="different-apple-user")

        response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("cards.apple_views._decode_apple_identity_token")
    @patch("cards.apple_views._exchange_apple_code")
    def test_nonce_must_match_verified_token(self, exchange, decode):
        exchange.return_value = {"id_token": "server-id-token"}
        decode.return_value = self.claims(nonce="different-nonce")

        response = self.post()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SocialAccount.objects.exists())

    def test_endpoint_rejects_get(self):
        self.assertEqual(self.client.get(reverse("native_apple_login")).status_code, 405)


class AppleButtonComplianceTests(TestCase):
    def test_login_template_uses_apple_generated_artwork_without_custom_logo_svg(self):
        template = Path(settings.BASE_DIR, "templates", "registration", "login.html").read_text(encoding="utf-8")
        self.assertIn("https://appleid.cdn-apple.com/appleid/button", template)
        self.assertNotIn("<svg viewBox=\"0 0 24 24\"", template)
        self.assertIn("data-native-url", template)

    def test_ios_release_entitlements_include_sign_in_with_apple(self):
        script = Path(settings.BASE_DIR, "mobile", "ci", "prepare-ios-release.rb").read_text(encoding="utf-8")
        self.assertIn("com.apple.developer.applesignin", script)
        self.assertIn("['Default']", script)
