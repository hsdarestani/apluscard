from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Business, Wallet


@override_settings(
    APPLE_WALLET_ENABLED=True,
    APPLE_WALLET_PASS_TYPE_ID="pass.de.sams.member",
    APPLE_WALLET_TEAM_ID="TEAM123456",
)
class AppleWalletHandoffTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="wallet-handoff", password="secret")
        self.business = Business.objects.create(name="Sams Club Lounge", slug="wallet-handoff")
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.user,
            display_name="Ashkan Dian",
        )
        self.client.force_login(self.user)

    @patch("cards.release_views.build_pkpass", return_value=b"signed-pkpass")
    def test_native_app_can_request_short_lived_safari_download(self, build_pkpass):
        link_response = self.client.get(reverse("apple_wallet_link"))
        self.assertEqual(link_response.status_code, 200)
        download_url = link_response.json()["url"]
        download_path = urlparse(download_url).path
        self.assertTrue(download_path.startswith("/wallet/download/"))
        self.assertEqual(link_response["Cache-Control"], "private, no-store")

        self.client.logout()
        download_response = self.client.get(download_path)
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.content, b"signed-pkpass")
        self.assertEqual(download_response["Content-Type"], "application/vnd.apple.pkpass")
        self.assertIn("Sams-Club-Lounge", download_response["Content-Disposition"])
        build_pkpass.assert_called_once()

    def test_tampered_wallet_download_link_is_rejected(self):
        response = self.client.get("/wallet/download/not-a-valid-signed-token/")
        self.assertEqual(response.status_code, 404)
