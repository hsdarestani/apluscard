from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from .models import Business, LedgerEntry, Membership, Wallet
from .services import MANAGER_ROLES, post_wallet_entry, require_role


class WalletServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="Test Lounge", slug="test-lounge")
        self.owner = User.objects.create_user(username="owner", password="test")
        self.staff = User.objects.create_user(username="staff", password="test")
        self.customer = User.objects.create_user(username="customer", password="test")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        self.wallet = Wallet.objects.create(business=self.business, owner=self.customer, display_name="Customer")

    def test_topup_and_purchase_update_balance_and_ledger(self):
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount="30", actor=self.staff)
        self.wallet.refresh_from_db()
        self.assertEqual(str(self.wallet.balance), "70.00")
        self.assertEqual(self.wallet.ledger_entries.count(), 2)

    def test_purchase_cannot_make_balance_negative(self):
        with self.assertRaises(ValidationError):
            post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount="1", actor=self.staff)

    def test_staff_cannot_use_manager_permission(self):
        with self.assertRaises(PermissionDenied):
            require_role(self.staff, self.business, MANAGER_ROLES)
