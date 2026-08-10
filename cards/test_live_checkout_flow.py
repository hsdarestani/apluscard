from django.test import TestCase
from django.urls import reverse

from .models import LedgerEntry, PaymentRequest
from .services import post_wallet_entry
from .tests import PlatformMixin


class LiveCheckoutFlowTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(
            wallet=self.wallet,
            entry_type=LedgerEntry.Type.TOPUP,
            amount="20.00",
            actor=self.owner,
        )

    def test_staff_api_accepts_same_static_uuid_shown_by_apple_wallet(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("api_staff_charge"),
            {
                "wallet_token": str(self.wallet.qr_token),
                "location_id": str(self.location_1.pk),
                "amount": "10.00",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        payment = PaymentRequest.objects.get()
        self.assertEqual(payment.wallet, self.wallet)
        self.assertEqual(payment.location, self.location_1)
        self.assertTrue(payment.customer_confirmation_required)
        self.assertEqual(str(payment.base_amount), "10.00")

    def test_customer_pending_api_immediately_exposes_staff_request(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("api_staff_charge"),
            {
                "wallet_token": str(self.wallet.qr_token),
                "location_id": str(self.location_1.pk),
                "amount": "10.00",
            },
            content_type="application/json",
        )

        self.client.force_login(self.customer)
        response = self.client.get(reverse("api_pending_payments"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["base_amount"], "10.00")
        self.assertEqual(payload[0]["status"], PaymentRequest.Status.PENDING)

    def test_customer_dashboard_uses_static_wallet_parity_qr_and_live_payment_polling(self):
        self.client.force_login(self.customer)
        session = self.client.session
        session["active_location_id"] = str(self.location_1.pk)
        session.save()

        response = self.client.get(reverse("customer_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mitglieds-QR · identisch mit Apple Wallet")
        self.assertContains(response, reverse("api_pending_payments"))
        self.assertContains(response, "checkPendingPayments")
        self.assertNotContains(response, "data-refresh-url")

    def test_staff_dashboard_submits_without_redirect_and_shows_explicit_success_state(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-api-url="{reverse("api_staff_charge")}"', html=False)
        self.assertContains(response, "Zahlungsanfrage gesendet ✓")
        self.assertContains(response, "Neue Zahlung starten")
        self.assertContains(response, "Wird an Kunden gesendet")
