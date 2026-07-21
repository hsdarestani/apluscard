from datetime import date, timedelta

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

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

    def test_underage_apple_customer_is_rejected(self):
        underage = date.today() - timedelta(days=365 * 17)
        response = self.client.post(reverse("complete_customer_profile"), self.payload(underage))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "erst ab 18 Jahren möglich")
        self.assertFalse(Wallet.objects.filter(owner=self.user).exists())

    def test_existing_wallet_skips_profile_completion(self):
        Wallet.objects.create(business=self.business, owner=self.user, display_name="Anna Beispiel")
        response = self.client.get(reverse("complete_customer_profile"))
        self.assertRedirects(response, reverse("dashboard"))


class GermanInterfaceTests(TestCase):
    def test_login_page_contains_apple_button_in_german(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mit Apple fortfahren")
        self.assertContains(response, "Willkommen zurück")

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
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            body = response.content.decode("utf-8")
            for text in forbidden:
                self.assertNotIn(text, body)
