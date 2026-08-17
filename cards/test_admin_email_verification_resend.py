from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .email_verification_models import EmailVerificationAttempt
from .models import MemberProfile


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    APP_PUBLIC_BASE_URL="https://app.samsclublounge.de",
)
class MemberProfileAdminVerificationResendTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="verification-admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.member = user_model.objects.create_user(
            username="member-resend",
            email="member@example.com",
            password="test-password-123",
        )
        self.profile = MemberProfile.objects.create(
            user=self.member,
            email_verified=False,
        )
        self.client.force_login(self.admin)

    def test_changelist_shows_resend_button_for_unverified_member(self):
        response = self.client.get(reverse("admin:cards_memberprofile_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Erneut senden")
        self.assertContains(response, self.member.email)

    def test_single_resend_sends_mail_and_records_resend_attempt(self):
        url = reverse(
            "admin:cards_memberprofile_resend_verification",
            args=[self.profile.pk],
        )

        response = self.client.post(url, follow=False)

        self.assertRedirects(
            response,
            reverse("admin:cards_memberprofile_changelist"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.member.email])
        attempt = EmailVerificationAttempt.objects.get(user=self.member)
        self.assertEqual(attempt.trigger, EmailVerificationAttempt.Trigger.RESEND)
        self.assertEqual(attempt.status, EmailVerificationAttempt.Status.ACCEPTED)
        self.assertIn("https://app.samsclublounge.de/accounts/verify/", mail.outbox[0].body)

    def test_bulk_resend_only_sends_to_unverified_members(self):
        user_model = get_user_model()
        second_member = user_model.objects.create_user(
            username="member-resend-2",
            email="member2@example.com",
            password="test-password-123",
        )
        second_profile = MemberProfile.objects.create(
            user=second_member,
            email_verified=False,
        )
        verified_member = user_model.objects.create_user(
            username="member-verified",
            email="verified@example.com",
            password="test-password-123",
        )
        verified_profile = MemberProfile.objects.create(
            user=verified_member,
            email_verified=True,
        )

        response = self.client.post(
            reverse("admin:cards_memberprofile_changelist"),
            {
                "action": "resend_verification_selected",
                "_selected_action": [
                    str(self.profile.pk),
                    str(second_profile.pk),
                    str(verified_profile.pk),
                ],
                "index": "0",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        recipients = {message.to[0] for message in mail.outbox}
        self.assertEqual(recipients, {self.member.email, second_member.email})
        self.assertEqual(
            EmailVerificationAttempt.objects.filter(
                trigger=EmailVerificationAttempt.Trigger.RESEND,
                status=EmailVerificationAttempt.Status.ACCEPTED,
            ).count(),
            2,
        )
        self.assertFalse(
            EmailVerificationAttempt.objects.filter(user=verified_member).exists()
        )
