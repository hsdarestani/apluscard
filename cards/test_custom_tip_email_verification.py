from django.test import TestCase
from django.urls import reverse

from .models import LedgerEntry
from .services import create_payment_request, post_wallet_entry
from .tests import PlatformMixin


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

    def test_pending_payment_only_shows_free_tip_input(self):
        create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.staff,
            amount="10.00",
            customer_tip_required=True,
        )

        response = self.client.get(reverse("customer_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="tip_amount"', html=False)
        self.assertContains(response, "Gib deinen gewünschten Trinkgeldbetrag selbst ein.")
        self.assertNotContains(response, "data-tip-value")
        self.assertNotContains(response, ">0,10 €</button>", html=False)
        self.assertNotContains(response, ">1,00 €</button>", html=False)
        self.assertNotContains(response, ">Kein Trinkgeld</button>", html=False)


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
