from allauth.account.models import EmailAddress
from django.test import TestCase
from django.urls import reverse

from .models import LedgerEntry
from .services import create_payment_request, post_wallet_entry
from .tests import PlatformMixin
from .views import _verification_token


class CustomTipUiTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(
            wallet=self.wallet,
            entry_type=LedgerEntry.Type.TOPUP,
            amount="100.00",
            actor=self.owner,
        )
        self.client.force_login(self.customer)
        session = self.client.session
        session["active_location_id"] = str(self.location_1.pk)
        session.save()

    def test_pending_payment_shows_staff_selected_tip_without_customer_tip_input(self):
        create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.staff,
            amount="10.00",
            tip_amount="2.50",
            customer_confirmation_required=True,
        )

        response = self.client.get(reverse("customer_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trinkgeld:</strong> 2,50 €", html=False)
        self.assertContains(response, "Das Trinkgeld wurde vom Mitarbeiter eingetragen.")
        self.assertContains(response, 'type="hidden" name="tip_amount"', html=False)
        self.assertNotContains(response, "Trinkgeldbetrag (€)")
        self.assertNotContains(response, "Gib deinen gewünschten Trinkgeldbetrag selbst ein.")


class EmailVerificationStatusTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        self.client.force_login(self.customer)

    def test_status_endpoint_reads_current_database_state_without_cache(self):
        profile = self.customer.member_profile
        profile.email_verified = False
        profile.email_verified_at = None
        profile.save(update_fields=["email_verified", "email_verified_at"])

        response = self.client.get(reverse("email_verification_status"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"email_verified": False})
        self.assertIn("no-store", response["Cache-Control"])

        profile.email_verified = True
        profile.save(update_fields=["email_verified"])

        response = self.client.get(reverse("email_verification_status"))
        self.assertEqual(response.json(), {"email_verified": True})

    def test_member_profile_creation_is_visible_in_allauth_admin_state(self):
        address = EmailAddress.objects.get(
            user=self.customer,
            email__iexact=self.customer.email,
        )
        self.assertTrue(address.verified)
        self.assertTrue(address.primary)

    def test_verification_link_updates_member_and_allauth_state(self):
        EmailAddress.objects.filter(user=self.customer).delete()
        profile = self.customer.member_profile
        profile.email_verified = False
        profile.email_verified_at = None
        profile.save(update_fields=["email_verified", "email_verified_at"])

        address = EmailAddress.objects.get(
            user=self.customer,
            email__iexact=self.customer.email,
        )
        self.assertFalse(address.verified)

        response = self.client.get(
            reverse("verify_email", args=[_verification_token(self.customer)])
        )
        self.assertEqual(response.status_code, 302)

        profile.refresh_from_db()
        address.refresh_from_db()
        self.assertTrue(profile.email_verified)
        self.assertIsNotNone(profile.email_verified_at)
        self.assertTrue(address.verified)
