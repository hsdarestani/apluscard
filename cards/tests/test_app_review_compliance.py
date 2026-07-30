from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from cards.legal_forms import LegalAppleProfileCompletionForm, LegalCustomerRegistrationForm
from cards.security_middleware import SecurityHeadersMiddleware


class OptionalMemberDetailsTests(TestCase):
    def test_email_registration_accepts_blank_phone_and_birth_date(self):
        form = LegalCustomerRegistrationForm(
            data={
                "first_name": "Sams",
                "last_name": "Member",
                "email": "optional-fields@example.com",
                "phone": "",
                "birth_date": "",
                "password1": "A-Strong-Test-Password-2026!",
                "password2": "A-Strong-Test-Password-2026!",
                "age_confirmed": "on",
                "accept_terms": "on",
                "acknowledge_privacy": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data["phone"], "")
        self.assertIsNone(form.cleaned_data["birth_date"])
        self.assertFalse(form.fields["phone"].required)
        self.assertFalse(form.fields["birth_date"].required)

    def test_apple_profile_completion_accepts_blank_phone_and_birth_date(self):
        user = get_user_model().objects.create_user(
            username="apple-optional-fields",
            email="apple-optional-fields@example.com",
        )
        form = LegalAppleProfileCompletionForm(
            data={
                "first_name": "Apple",
                "last_name": "Member",
                "phone": "",
                "birth_date": "",
                "age_confirmed": "on",
                "accept_terms": "on",
                "acknowledge_privacy": "on",
            },
            user=user,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()
        user.refresh_from_db()
        self.assertEqual(form.cleaned_data["phone"], "")
        self.assertIsNone(user.member_profile.birth_date)
        self.assertTrue(user.member_profile.age_confirmed)

    def test_optional_values_are_validated_only_when_supplied(self):
        user = get_user_model().objects.create_user(
            username="apple-invalid-optional-fields",
            email="apple-invalid-optional-fields@example.com",
        )
        form = LegalAppleProfileCompletionForm(
            data={
                "first_name": "Apple",
                "last_name": "Member",
                "phone": "12",
                "birth_date": "",
                "age_confirmed": "on",
                "accept_terms": "on",
                "acknowledge_privacy": "on",
            },
            user=user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)
        self.assertNotIn("birth_date", form.errors)


class AppleButtonReviewComplianceTests(TestCase):
    def test_login_uses_complete_apple_generated_button_without_custom_logo(self):
        template = Path(settings.BASE_DIR, "templates", "registration", "login.html").read_text(encoding="utf-8")
        self.assertIn("https://appleid.cdn-apple.com/appleid/button", template)
        self.assertIn("border=true", template)
        self.assertIn("type=continue", template)
        self.assertNotIn("<svg", template)
        self.assertNotIn("apple-logo", template)

    def test_security_policy_allows_official_apple_button_artwork(self):
        middleware = SecurityHeadersMiddleware(lambda request: HttpResponse("ok"))
        response = middleware(RequestFactory().get("/accounts/login/"))
        policy = response["Content-Security-Policy"]
        self.assertIn("img-src 'self' data: blob: https://appleid.cdn-apple.com", policy)

    def test_optional_fields_are_clearly_labelled_in_both_registration_flows(self):
        registration = Path(settings.BASE_DIR, "cards", "templates", "cards", "register.html").read_text(encoding="utf-8")
        apple_completion = Path(
            settings.BASE_DIR,
            "cards",
            "templates",
            "cards",
            "complete_customer_profile.html",
        ).read_text(encoding="utf-8")
        for template in (registration, apple_completion):
            self.assertIn("Mobilnummer <small>(optional)</small>", template)
            self.assertIn("Geburtsdatum <small>(optional)</small>", template)
            self.assertIn("beide Felder leer lassen", template)
