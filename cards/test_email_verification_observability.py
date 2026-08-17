import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .email_verification_models import EmailVerificationAttempt
from .emailing import send_verification_email
from .models import Business, MemberProfile, Wallet
from .views import _verification_token


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    APP_PUBLIC_BASE_URL="https://app.samsclublounge.de",
    ALLOWED_HOSTS=["testserver", "legacy.example.test"],
)
class EmailVerificationObservabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="viki-test",
            email="viki.arya@example.test",
            password="safe-test-password",
            first_name="Viki",
        )
        self.profile = MemberProfile.objects.create(
            user=self.user,
            email_verified=False,
            age_confirmed=True,
        )
        self.business = Business.objects.create(
            name="Sams Club Lounge",
            slug="shisha-bar",
            is_active=True,
        )
        Wallet.objects.create(
            business=self.business,
            owner=self.user,
            display_name="Viki",
            email=self.user.email,
        )
        self.factory = RequestFactory()

    def test_send_uses_canonical_public_host_and_records_backend_acceptance(self):
        request = self.factory.post(
            "/accounts/register/",
            HTTP_HOST="legacy.example.test",
        )

        self.assertTrue(send_verification_email(request, self.user))

        attempt = EmailVerificationAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.ACCEPTED)
        self.assertEqual(attempt.trigger, EmailVerificationAttempt.Trigger.REGISTRATION)
        self.assertEqual(attempt.request_host, "legacy.example.test")
        self.assertIsNotNone(attempt.accepted_at)
        self.assertIn("https://app.samsclublounge.de/accounts/verify/", mail.outbox[0].body)
        self.assertNotIn("legacy.example.test/accounts/verify/", mail.outbox[0].body)
        self.assertIn(f"attempt={attempt.pk}", mail.outbox[0].body)
        self.assertIn("30 Tage gültig", mail.outbox[0].body)

    def test_successful_click_confirms_member_logs_in_and_goes_to_dashboard(self):
        request = self.factory.post("/accounts/register/", HTTP_HOST="testserver")
        send_verification_email(request, self.user)
        attempt = EmailVerificationAttempt.objects.get(user=self.user)
        token = _verification_token(self.user)

        response = self.client.get(
            reverse("verify_email", args=[token]),
            {"attempt": str(attempt.pk)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.profile.refresh_from_db()
        attempt.refresh_from_db()
        self.assertTrue(self.profile.email_verified)
        self.assertIsNotNone(self.profile.email_verified_at)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.CONFIRMED)
        self.assertEqual(attempt.click_count, 1)
        self.assertIsNotNone(attempt.clicked_at)
        self.assertIsNotNone(attempt.confirmed_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_bad_attempt_parameter_cannot_break_a_valid_signed_token(self):
        request = self.factory.post("/accounts/register/", HTTP_HOST="testserver")
        send_verification_email(request, self.user)
        attempt = EmailVerificationAttempt.objects.get(user=self.user)
        token = _verification_token(self.user)

        response = self.client.get(
            reverse("verify_email", args=[token]),
            {"attempt": "00000000-0000-4000-8000-000000000001"},
        )

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        attempt.refresh_from_db()
        self.assertTrue(self.profile.email_verified)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.CONFIRMED)

    def test_invalid_token_does_not_corrupt_an_unrelated_attempt(self):
        request = self.factory.post("/accounts/register/", HTTP_HOST="testserver")
        send_verification_email(request, self.user)
        attempt = EmailVerificationAttempt.objects.get(user=self.user)

        response = self.client.get(
            reverse("verify_email", args=["broken-token"]),
            {"attempt": str(attempt.pk)},
        )

        self.assertEqual(response.status_code, 302)
        attempt.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_verified)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.ACCEPTED)
        self.assertEqual(attempt.click_count, 0)

    def test_expired_but_genuinely_signed_link_automatically_sends_a_fresh_link(self):
        old_timestamp = time.time() - (31 * 24 * 60 * 60)
        with patch("django.core.signing.time.time", return_value=old_timestamp):
            expired_token = _verification_token(self.user)

        response = self.client.get(reverse("verify_email", args=[expired_token]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        attempt = EmailVerificationAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.trigger, EmailVerificationAttempt.Trigger.RESEND)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.ACCEPTED)
        self.assertIn("https://app.samsclublounge.de/accounts/verify/", mail.outbox[0].body)

    def test_repeated_click_is_idempotent_and_still_opens_member_session(self):
        self.profile.email_verified = True
        self.profile.save(update_fields=["email_verified"])
        token = _verification_token(self.user)

        response = self.client.get(reverse("verify_email", args=[token]))

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)
        self.assertIsNotNone(self.profile.email_verified_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_send_failure_is_persisted_with_error_details(self):
        request = self.factory.post("/accounts/resend-verification/", HTTP_HOST="testserver")

        with patch("cards.emailing.EmailMultiAlternatives.send", side_effect=OSError("smtp down")):
            with self.assertRaises(OSError):
                send_verification_email(request, self.user)

        attempt = EmailVerificationAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.trigger, EmailVerificationAttempt.Trigger.RESEND)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.FAILED)
        self.assertEqual(attempt.error_class, "OSError")
        self.assertIn("smtp down", attempt.error_detail)
