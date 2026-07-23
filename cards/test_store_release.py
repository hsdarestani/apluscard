from django.test import TestCase, override_settings
from django.urls import reverse


class StoreReleaseEndpointTests(TestCase):
    @override_settings(APP_NAME="A+ Card", APP_SHORT_NAME="A+ Card")
    def test_manifest_uses_aplus_identity(self):
        response = self.client.get(reverse("manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        payload = response.json()
        self.assertEqual(payload["name"], "A+ Card")
        self.assertEqual(payload["short_name"], "A+ Card")
        self.assertEqual(payload["display"], "standalone")
        self.assertEqual(payload["start_url"], "/")
        self.assertIn(
            {"src": "/app-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            payload["icons"],
        )

    def test_png_icons_are_generated_in_store_sizes(self):
        for size in (192, 512):
            response = self.client.get(reverse("app_icon", args=[size]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(response.content), 1000)
        self.assertEqual(self.client.get(reverse("app_icon", args=[256])).status_code, 404)

    @override_settings(
        ANDROID_PACKAGE_NAME="de.aplussolution.apluscard",
        ANDROID_APP_SIGNING_SHA256=[
            "AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA:AA"
        ],
    )
    def test_assetlinks_contains_google_play_signing_identity(self):
        response = self.client.get(reverse("android_asset_links"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["target"]["package_name"], "de.aplussolution.apluscard")
        self.assertEqual(len(payload[0]["target"]["sha256_cert_fingerprints"]), 1)
        self.assertIn("delegate_permission/common.handle_all_urls", payload[0]["relation"])

    @override_settings(
        ANDROID_PACKAGE_NAME="de.aplussolution.apluscard",
        ANDROID_APP_SIGNING_SHA256=["not-a-fingerprint"],
    )
    def test_assetlinks_does_not_publish_invalid_fingerprint(self):
        response = self.client.get(reverse("android_asset_links"))
        self.assertEqual(response.json(), [])

    @override_settings(
        IOS_APP_TEAM_ID="A1B2C3D4E5",
        IOS_BUNDLE_ID="de.aplussolution.apluscard",
    )
    def test_apple_association_contains_aplus_bundle(self):
        response = self.client.get(reverse("apple_app_site_association"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        app_id = "A1B2C3D4E5.de.aplussolution.apluscard"
        self.assertEqual(payload["applinks"]["details"][0]["appIDs"], [app_id])
        self.assertEqual(payload["webcredentials"]["apps"], [app_id])
