from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .email_verification_models import EmailVerificationAttempt
from .models import Business, MemberProfile, Membership, Wallet


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    APP_PUBLIC_BASE_URL="https://app.samsclublounge.de",
)
class ManagerEmailVerificationControlsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.business = Business.objects.create(name="SAMS Test", slug="sams-test")
        self.manager = user_model.objects.create_user(
            username="owner-manager",
            email="owner@example.com",
            password="test-password-123",
        )
        Membership.objects.create(
            user=self.manager,
            business=self.business,
            role=Membership.Role.OWNER,
        )
        self.member = user_model.objects.create_user(
            username="member-email-check",
            email="member@example.com",
            password="test-password-123",
        )
        self.profile = MemberProfile.objects.create(
            user=self.member,
            email_verified=False,
        )
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.member,
            display_name="Member Test",
            email=self.member.email,
        )
        self.client.force_login(self.manager)

    def test_manager_can_resend_verification_from_wallet(self):
        response = self.client.post(
            reverse("manager_resend_verification", args=[self.wallet.pk]),
            follow=False,
        )

        self.assertRedirects(
            response,
            reverse("manager_wallet_detail", args=[self.wallet.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.member.email])
        attempt = EmailVerificationAttempt.objects.get(user=self.member)
        self.assertEqual(attempt.trigger, EmailVerificationAttempt.Trigger.RESEND)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.ACCEPTED)
        self.assertIn("https://cards.smarbiz.sbs/accounts/verify/", mail.outbox[0].body)

    def test_wallet_page_shows_latest_verification_status_and_resend_button(self):
        self.client.post(
            reverse("manager_resend_verification", args=[self.wallet.pk]),
            follow=False,
        )

        response = self.client.get(
            reverse("manager_wallet_detail", args=[self.wallet.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E-Mail-Bestätigung offen")
        self.assertContains(response, "Vom Mail-Backend angenommen")
        self.assertContains(response, "Bestätigungs-E-Mail erneut senden")

    def test_verified_member_is_not_resent(self):
        self.profile.email_verified = True
        self.profile.save(update_fields=["email_verified"])

        response = self.client.post(
            reverse("manager_resend_verification", args=[self.wallet.pk]),
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(EmailVerificationAttempt.objects.filter(user=self.member).exists())