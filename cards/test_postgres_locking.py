from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import LedgerEntry
from .services import create_payment_request, finalize_payment_request, post_wallet_entry
from .tests import PlatformMixin


class PostgreSqlLockingRegressionTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()

    def test_owner_topup_view_succeeds_and_renders_detail_page(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("manager_topup", args=[self.wallet.pk]),
            {"amount": "25.00", "description": "Barzahlung erhalten", "order_reference": "REGRESSION-1"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("25.00"))
        entry = self.wallet.ledger_entries.get(entry_type=LedgerEntry.Type.TOPUP)
        self.assertContains(response, entry.bill_number)

    def test_payment_confirmation_succeeds_with_nullable_owner_relation(self):
        self.settings.require_customer_confirmation = True
        self.settings.save(update_fields=["require_customer_confirmation"])
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="50.00", actor=self.owner)
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="10.00", tip_amount="0")
        payment = finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_amount="0")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("40.00"))
        self.assertEqual(payment.purchase_entry.entry_type, LedgerEntry.Type.PURCHASE)
