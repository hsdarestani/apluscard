from datetime import date

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .legal_models import AccountDeletionRequest, LegalAcceptance, LegalConfiguration, PrivacyPreference
from .legal_services import has_current_acceptances, record_legal_acceptances
from .models import Business, Location, MemberProfile, Wallet


@override_settings(
    DEFAULT_BUSINESS_SLUG="shisha-bar",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LegalPrivacyFlowTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS Club Lounge", slug="shisha-bar")
        Location.objects.create(
            business=self.business,
            name="SAMS Mitte",
            slug="mitte",
            address="Musterstraße 1\n60311 Frankfurt am Main",
        )
        self.legal = LegalConfiguration.objects.create(
            business=self.business,
            app_display_name="SAMS Club Lounge",
            controller_name="SAMS Beispiel GmbH",
            controller_address="Musterstraße 1\n60311 Frankfurt am Main",
            contact_email="kontakt@example.com",
            privacy_email="datenschutz@example.com",
            terms_version="1.0",
            privacy_version="1.0",
        )

    def registration_payload(self, email="kunde@example.com"):
        return {
            "first_name": "Anna",
            "last_name": "Beispiel",
            "email": email,
            "phone": "+49 160 1234567",
            "birth_date": date(1990, 5, 12).isoformat(),
            "age_confirmed": "on",
            "password1": "SicheresPasswort-2026!",
            "password2": "SicheresPasswort-2026!",
            "accept_terms": "on",
            "acknowledge_privacy": "on",
            "marketing_push_consent": "on",
        }

    def test_public_legal_pages_exist_per_app(self):
        routes = [
            reverse("app_terms", args=[self.business.slug]),
            reverse("app_privacy_policy", args=[self.business.slug]),
            reverse("app_imprint", args=[self.business.slug]),
            reverse("app_account_deletion", args=[self.business.slug]),
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "SAMS")

    def test_registration_requires_legal_confirmation(self):
        payload = self.registration_payload()
        payload.pop("accept_terms")
        response = self.client.post(reverse("register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(email="kunde@example.com").exists())

    def test_registration_records_versions_and_optional_marketing_choice(self):
        response = self.client.post(reverse("register"), self.registration_payload())
        self.assertRedirects(response, reverse("customer_dashboard"))
        user = get_user_model().objects.get(email="kunde@example.com")
        wallet = Wallet.objects.get(owner=user)
        self.assertTrue(has_current_acceptances(user, self.business))
        self.assertEqual(
            set(LegalAcceptance.objects.filter(user=user).values_list("document_type", flat=True)),
            {LegalAcceptance.DocumentType.TERMS, LegalAcceptance.DocumentType.PRIVACY},
        )
        self.assertEqual(wallet.business, self.business)
        self.assertTrue(PrivacyPreference.objects.get(user=user, business=self.business).marketing_push_enabled)

    def test_existing_customer_is_redirected_when_version_changes(self):
        user = get_user_model().objects.create_user(username="alt@example.com", email="alt@example.com", password="Passwort-2026!")
        MemberProfile.objects.create(user=user, birth_date=date(1990, 1, 1), age_confirmed=True, email_verified=True)
        Wallet.objects.create(business=self.business, owner=user, display_name="Alter Kunde", email=user.email)
        self.client.force_login(user)
        record_legal_acceptances(
            user=user,
            business=self.business,
            request=self.client.get(reverse("terms")).wsgi_request,
            source=LegalAcceptance.Source.RECONFIRMATION,
        )
        self.assertEqual(self.client.get(reverse("customer_dashboard")).status_code, 200)
        self.legal.terms_version = "2.0"
        self.legal.save(update_fields=["terms_version"])
        response = self.client.get(reverse("customer_dashboard"))
        self.assertRedirects(response, reverse("legal_acceptance"), fetch_redirect_response=False)
        response = self.client.post(reverse("legal_acceptance"), {"accept_terms": "on", "acknowledge_privacy": "on"})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(has_current_acceptances(user, self.business))

    def test_apple_profile_completion_records_legal_versions(self):
        user = get_user_model().objects.create_user(username="apple@example.com", email="apple@example.com")
        SocialAccount.objects.create(user=user, provider="apple", uid="apple-uid")
        self.client.force_login(user)
        response = self.client.post(
            reverse("complete_customer_profile"),
            {
                "first_name": "Apple",
                "last_name": "Kunde",
                "phone": "+49 170 1234567",
                "birth_date": "1992-03-04",
                "age_confirmed": "on",
                "accept_terms": "on",
                "acknowledge_privacy": "on",
            },
        )
        self.assertRedirects(response, reverse("customer_dashboard"))
        self.assertTrue(Wallet.objects.filter(owner=user, business=self.business).exists())
        self.assertTrue(has_current_acceptances(user, self.business))

    def test_public_account_deletion_request_can_be_submitted(self):
        response = self.client.post(
            reverse("app_account_deletion", args=[self.business.slug]),
            {
                "email": "delete@example.com",
                "member_number": "12345678",
                "reason": "Bitte löschen",
                "confirmation": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        deletion_request = AccountDeletionRequest.objects.get(email="delete@example.com")
        self.assertContains(response, deletion_request.reference_number)
        self.assertEqual(deletion_request.status, AccountDeletionRequest.Status.RECEIVED)

    def test_privacy_choices_can_be_withdrawn(self):
        user = get_user_model().objects.create_user(username="privacy@example.com", email="privacy@example.com", password="Passwort-2026!")
        MemberProfile.objects.create(user=user, birth_date=date(1990, 1, 1), age_confirmed=True, email_verified=True)
        Wallet.objects.create(business=self.business, owner=user, display_name="Privacy Kunde", email=user.email)
        preference = PrivacyPreference.objects.create(user=user, business=self.business, marketing_push_enabled=True)
        self.client.force_login(user)
        record_legal_acceptances(
            user=user,
            business=self.business,
            request=self.client.get(reverse("terms")).wsgi_request,
            source=LegalAcceptance.Source.RECONFIRMATION,
            marketing_push=True,
        )
        response = self.client.post(reverse("privacy_choices"), {})
        self.assertRedirects(response, reverse("privacy_choices"))
        preference.refresh_from_db()
        self.assertFalse(preference.marketing_push_enabled)
        self.assertIsNotNone(preference.withdrawn_at)
