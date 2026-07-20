from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

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


@override_settings(DEFAULT_BUSINESS_SLUG="shisha-bar")
class CustomerRegistrationTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="shisha-bar")

    def registration_payload(self, email="new.member@example.com"):
        return {
            "first_name": "Lena",
            "last_name": "Sommer",
            "email": email,
            "phone": "+49 160 1234567",
            "password1": "SamsMember2026!",
            "password2": "SamsMember2026!",
        }

    def test_registration_page_is_available(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member werden")

    def test_registration_creates_user_wallet_and_session(self):
        response = self.client.post(reverse("register"), self.registration_payload())
        self.assertRedirects(response, reverse("customer_dashboard"))

        User = get_user_model()
        user = User.objects.get(email="new.member@example.com")
        self.assertEqual(user.username, "new.member@example.com")
        wallet = Wallet.objects.get(owner=user, business=self.business)
        self.assertEqual(wallet.display_name, "Lena Sommer")
        self.assertEqual(wallet.phone, "+49 160 1234567")
        self.assertEqual(str(wallet.balance), "0.00")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_duplicate_email_is_rejected(self):
        User = get_user_model()
        User.objects.create_user(username="existing@example.com", email="existing@example.com", password="Existing2026!")
        response = self.client.post(reverse("register"), self.registration_payload("existing@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "besteht bereits ein Konto")
        self.assertEqual(Wallet.objects.count(), 0)
