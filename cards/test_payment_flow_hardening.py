from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BusinessSettingsForm
from .models import LedgerEntry, PaymentRequest
from .services import create_payment_request, post_wallet_entry
from .tests import PlatformMixin


class PaymentFlowHardeningTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(
            wallet=self.wallet,
            entry_type=LedgerEntry.Type.TOPUP,
            amount="100.00",
            actor=self.owner,
        )

    def _pending_checkout(self, *, amount="12.00", tip="2.00"):
        return create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.staff,
            amount=amount,
            tip_amount=tip,
            customer_confirmation_required=True,
        )

    def test_staff_checkout_keeps_tip_locked_until_customer_confirmation(self):
        payment = self._pending_checkout()

        self.assertEqual(payment.status, PaymentRequest.Status.PENDING)
        self.assertTrue(payment.customer_confirmation_required)
        self.assertEqual(payment.tip_selected_amount, Decimal("2.00"))
        self.assertEqual(payment.tip_amount, Decimal("0.00"))
        self.assertFalse(
            LedgerEntry.objects.filter(
                wallet=self.wallet,
                entry_type=LedgerEntry.Type.PURCHASE,
            ).exists()
        )

    def test_explicit_management_immediate_charge_still_finalizes(self):
        payment = create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.owner,
            amount="5.00",
            tip_amount="1.00",
            force_immediate=True,
        )

        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertFalse(payment.customer_confirmation_required)
        self.assertEqual(payment.tip_amount, Decimal("1.00"))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("94.00"))

    def test_customer_pending_api_persists_expired_status(self):
        payment = self._pending_checkout(amount="10.00", tip="2.00")
        PaymentRequest.objects.filter(pk=payment.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.client.force_login(self.customer)
        response = self.client.get(reverse("api_pending_payments"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.EXPIRED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    def test_staff_status_poll_persists_expired_status(self):
        payment = self._pending_checkout(amount="8.00", tip="1.00")
        PaymentRequest.objects.filter(pk=payment.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("api_staff_payment_status", args=[payment.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], PaymentRequest.Status.EXPIRED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.EXPIRED)

    def test_manager_settings_no_longer_exposes_confirmation_toggle(self):
        form = BusinessSettingsForm(instance=self.settings)
        self.assertNotIn("require_customer_confirmation", form.fields)
