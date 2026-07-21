from django.test import SimpleTestCase
from django.urls import resolve, reverse


class AppleCallbackUrlTests(SimpleTestCase):
    def test_named_apple_callback_uses_registered_sams_url(self):
        self.assertEqual(reverse("apple_callback"), "/accounts/apple/callback/")

    def test_registered_callback_route_is_available(self):
        match = resolve("/accounts/apple/callback/")
        self.assertEqual(match.url_name, "apple_callback")

    def test_apple_callback_only_accepts_post(self):
        response = self.client.get("/accounts/apple/callback/")
        self.assertEqual(response.status_code, 405)
