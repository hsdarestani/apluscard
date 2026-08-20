from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import LedgerEntry, PaymentRequest
from .services import create_payment_request, post_wallet_entry
from .tests import PlatformMixin


class CustomerConfirmationRegressionTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(
            wallet=self.wallet,
            entry_type=LedgerEntry.Type.TOPUP,
            amount="100.00",
            actor=self.owner,
        )

    def _pending_payment(self, *, amount="18.00", tip="2.00"):
        return create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.staff,
            amount=amount,
            tip_amount=tip,
            customer_confirmation_required=True,
        )

    def test_web_confirmation_accepts_german_formatted_legacy_hidden_tip(self):
        payment = self._pending_payment()
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("customer_confirm_payment", args=[payment.pk]),
            {"tip_amount": "2,00"},
        )

        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payment.tip_amount, Decimal("2.00"))
        self.assertEqual(self.wallet.balance, Decimal("80.00"))

    def test_api_confirmation_needs_no_customer_tip_and_uses_staff_tip(self):
        payment = self._pending_payment(amount="10.00", tip="1.50")
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("api_confirm_payment", args=[payment.pk]),
            {},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payment.tip_amount, Decimal("1.50"))
        self.assertEqual(response.json()["tip_amount"], "1.50")
