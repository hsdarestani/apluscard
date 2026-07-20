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

    def test_wallet_gets_unique_eight_digit_member_number(self):
        second_wallet = Wallet.objects.create(business=self.business, display_name="Second Customer")
        self.assertEqual(len(self.wallet.member_number), 8)
        self.assertTrue(self.wallet.member_number.isdigit())
        self.assertNotEqual(self.wallet.member_number, second_wallet.member_number)

    def test_topup_and_purchase_update_balance_and_ledger(self):
        topup = post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)
        purchase = post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount="30", actor=self.staff)
        self.wallet.refresh_from_db()
        self.assertEqual(str(self.wallet.balance), "70.00")
        self.assertEqual(self.wallet.ledger_entries.count(), 2)
        self.assertTrue(topup.bill_number.startswith("B-"))
        self.assertTrue(purchase.bill_number.startswith("B-"))
        self.assertNotEqual(topup.bill_number, purchase.bill_number)

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
        self.assertEqual(len(wallet.member_number), 8)
        self.assertTrue(wallet.member_number.isdigit())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_duplicate_email_is_rejected(self):
        User = get_user_model()
        User.objects.create_user(username="existing@example.com", email="existing@example.com", password="Existing2026!")
        response = self.client.post(reverse("register"), self.registration_payload("existing@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "besteht bereits ein Konto")
        self.assertEqual(Wallet.objects.count(), 0)


class ManagerQrScanTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="sams")
        self.other_business = Business.objects.create(name="Other Lounge", slug="other")
        self.owner = User.objects.create_user(username="scan-owner", password="test")
        self.staff = User.objects.create_user(username="scan-staff", password="test")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        self.wallet = Wallet.objects.create(business=self.business, display_name="SAMS Member")
        self.other_wallet = Wallet.objects.create(business=self.other_business, display_name="Other Member")

    def test_owner_scan_redirects_to_member_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_wallet_scan"), {"token": str(self.wallet.qr_token)})
        self.assertRedirects(response, reverse("manager_wallet_detail", args=[self.wallet.pk]))

    def test_owner_scan_accepts_uuid_inside_full_qr_content(self):
        self.client.force_login(self.owner)
        qr_content = f"https://cards.example/member/{self.wallet.qr_token}/"
        response = self.client.get(reverse("manager_wallet_scan"), {"token": qr_content})
        self.assertRedirects(response, reverse("manager_wallet_detail", args=[self.wallet.pk]))

    def test_owner_cannot_open_wallet_from_another_business_by_scan(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_wallet_scan"), {"token": str(self.other_wallet.qr_token)})
        self.assertRedirects(response, reverse("manager_dashboard"))

    def test_staff_cannot_use_manager_scan(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manager_wallet_scan"), {"token": str(self.wallet.qr_token)})
        self.assertEqual(response.status_code, 403)

    def test_invalid_qr_returns_to_manager_dashboard(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_wallet_scan"), {"token": "not-a-member-code"})
        self.assertRedirects(response, reverse("manager_dashboard"))


class BillAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="bill-lounge")
        self.other_business = Business.objects.create(name="Other Lounge", slug="bill-other")
        self.owner = User.objects.create_user(username="bill-owner", password="test")
        self.staff = User.objects.create_user(username="bill-staff", password="test")
        self.customer = User.objects.create_user(username="bill-customer", password="test")
        self.outsider = User.objects.create_user(username="bill-outsider", password="test")
        self.other_staff = User.objects.create_user(username="other-staff", password="test")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        Membership.objects.create(user=self.other_staff, business=self.other_business, role=Membership.Role.STAFF)
        self.wallet = Wallet.objects.create(business=self.business, owner=self.customer, display_name="Bill Customer")
        self.entry = post_wallet_entry(
            wallet=self.wallet,
            entry_type=LedgerEntry.Type.TOPUP,
            amount="50.00",
            actor=self.owner,
            description="Cash top-up",
        )

    def test_customer_can_open_own_bill(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("bill_detail", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.entry.bill_number)
        self.assertContains(response, self.wallet.member_number)

    def test_owner_and_staff_can_open_business_bill(self):
        for user in (self.owner, self.staff):
            self.client.force_login(user)
            response = self.client.get(reverse("bill_detail", args=[self.entry.pk]))
            self.assertEqual(response.status_code, 200)

    def test_unrelated_customer_cannot_open_bill(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("bill_detail", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 403)

    def test_staff_from_another_business_cannot_open_bill(self):
        self.client.force_login(self.other_staff)
        response = self.client.get(reverse("bill_detail", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 403)
