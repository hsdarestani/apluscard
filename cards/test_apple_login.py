from datetime import date, timedelta
from unittest.mock import patch

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from .adapters import SamsAccountAdapter
from .models import Business, MemberProfile, Wallet


@override_settings(DEFAULT_BUSINESS_SLUG="shisha-bar")
class AppleCustomerFlowTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS Club Lounge", slug="shisha-bar")
        self.user = get_user_model().objects.create_user(
            username="apple-kunde@example.com",
            email="apple-kunde@example.com",
            first_name="Anna",
            last_name="Beispiel",
        )
        SocialAccount.objects.create(user=self.user, provider="apple", uid="apple-123")
        self.client.force_login(self.user)

    def payload(self, birth_date=None):
        return {
            "first_name": "Anna",
            "last_name": "Beispiel",
            "phone": "+49 160 1234567",
            "birth_date": (birth_date or date(1990, 5, 12)).isoformat(),
            "age_confirmed": "on",
        }

    def test_apple_customer_can_complete_profile_and_receive_wallet(self):
        response = self.client.post(reverse("complete_customer_profile"), self.payload())
        self.assertRedirects(response, reverse("customer_dashboard"))
        wallet = Wallet.objects.get(owner=self.user)
        profile = MemberProfile.objects.get(user=self.user)
        self.assertEqual(wallet.business, self.business)
        self.assertEqual(wallet.phone, "+49 160 1234567")
        self.assertTrue(profile.age_confirmed)
        self.assertTrue(profile.email_verified)

    def test_repeated_profile_completion_never_creates_a_second_wallet(self):
        first = self.client.post(reverse("complete_customer_profile"), self.payload())
        self.assertEqual(first.status_code, 302)
        second = self.client.post(reverse("complete_customer_profile"), self.payload())
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Wallet.objects.filter(owner=self.user, business=self.business).count(), 1)

    def test_underage_apple_customer_is_rejected(self):
        underage = date.today() - timedelta(days=365 * 17)
        response = self.client.post(reverse("complete_customer_profile"), self.payload(underage))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "erst ab 18 Jahren möglich")
        self.assertFalse(Wallet.objects.filter(owner=self.user).exists())

    def test_existing_wallet_skips_profile_completion(self):
        Wallet.objects.create(business=self.business, owner=self.user, display_name="Anna Beispiel")
        response = self.client.get(reverse("complete_customer_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 302)
        self.assertEqual(dashboard.url, reverse("customer_dashboard"))


class AppleCallbackSecurityTests(TestCase):
    def test_callback_is_explicitly_csrf_exempt_for_apple_form_post(self):
        callback = resolve("/accounts/apple/callback/").func
        self.assertTrue(getattr(callback, "csrf_exempt", False))

    @patch("cards.apple_views.allauth_apple_callback", return_value=HttpResponse("ok"))
    def test_cross_site_style_post_does_not_return_csrf_403(self, mocked_callback):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            "/accounts/apple/callback/",
            {"state": "test", "code": "test"},
            HTTP_HOST="cards.smarbiz.sbs",
            HTTP_X_FORWARDED_PROTO="https",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        mocked_callback.assert_called_once()

    @patch("cards.apple_views.allauth_apple_callback", side_effect=PermissionDenied)
    def test_stale_apple_session_returns_safe_retry_instead_of_403(self, _mocked_callback):
        response = self.client.post("/accounts/apple/callback/", {"state": "stale"})
        self.assertRedirects(response, reverse("login"))

    def test_callback_rejects_get_requests(self):
        response = self.client.get("/accounts/apple/callback/")
        self.assertEqual(response.status_code, 405)

    def test_first_login_redirect_does_not_depend_on_socialaccount_commit_timing(self):
        user = get_user_model().objects.create_user(
            username="apple-first-step@example.com",
            email="apple-first-step@example.com",
        )
        request = RequestFactory().get("/accounts/apple/login/callback/finish/")
        request.user = user
        self.assertEqual(
            SamsAccountAdapter().get_login_redirect_url(request),
            reverse("complete_customer_profile"),
        )


class GermanInterfaceTests(TestCase):
    def test_login_page_contains_apple_button_in_german(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mit Apple fortfahren")
        self.assertContains(response, "Willkommen zurück")

    def test_mobile_viewport_prevents_accidental_zoom(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "maximum-scale=1")
        self.assertContains(response, "minimum-scale=1")
        self.assertContains(response, "user-scalable=no")

    def test_public_pages_do_not_show_previous_english_titles(self):
        forbidden = [
            "Member Login",
            "Welcome back",
            "Private Member Experience",
            "Cashless Wallet",
            "Digital Member Card",
            "Offers & Reservations",
            "powered by",
        ]
        for route in (reverse("landing"), reverse("login"), reverse("register")):
            with self.subTest(route=route):
                response = self.client.get(route, follow=True)
                self.assertEqual(response.status_code, 200)
                body = response.content.decode("utf-8")
                for text in forbidden:
                    self.assertNotIn(text, body)
