from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .legal_models import LegalAcceptance, LegalConfiguration
from .models import AppNotification, Business, BusinessSettings, LedgerEntry, Location, MemberProfile, Membership, Offer, PaymentRequest, Wallet
from .services import OWNER_ROLES, active_offers_for, create_payment_request, finalize_payment_request, post_wallet_entry, require_role
from .views import _verification_token


class PlatformMixin:
    def create_platform(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="shisha-bar")
        self.settings = BusinessSettings.objects.create(business=self.business)
        self.location_1 = Location.objects.create(business=self.business, name="SAMS Nord", slug="nord", position=1)
        self.location_2 = Location.objects.create(business=self.business, name="SAMS Süd", slug="sued", position=2)
        self.owner = User.objects.create_user(username="owner-test", password="test")
        self.staff = User.objects.create_user(username="staff-test", password="test")
        self.customer = User.objects.create_user(username="customer@example.com", email="customer@example.com", password="test")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        MemberProfile.objects.create(user=self.customer, birth_date=date(1995, 5, 5), age_confirmed=True, email_verified=True, email_verified_at=timezone.now())
        self.wallet = Wallet.objects.create(business=self.business, owner=self.customer, display_name="Customer", email=self.customer.email)
        LegalConfiguration.objects.create(
            business=self.business,
            app_display_name=self.business.name,
            controller_name=self.business.name,
            terms_version="1.0",
            privacy_version="1.0",
        )
        for document_type in (LegalAcceptance.DocumentType.TERMS, LegalAcceptance.DocumentType.PRIVACY):
            LegalAcceptance.objects.create(
                user=self.customer,
                business=self.business,
                document_type=document_type,
                version="1.0",
                source=LegalAcceptance.Source.REGISTRATION,
                email_hash="test",
                member_number=self.wallet.member_number,
            )


class WalletServiceTests(PlatformMixin, TestCase):
    def setUp(self): self.create_platform()

    def test_wallet_gets_sequential_member_number_from_101(self):
        second_wallet = Wallet.objects.create(business=self.business, display_name="Second")
        self.assertEqual(self.wallet.member_number, "101")
        self.assertEqual(second_wallet.member_number, "102")

    def test_topup_and_purchase_update_shared_balance_across_locations(self):
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)
        payment = create_payment_request(wallet=self.wallet, location=self.location_2, actor=self.staff, amount="30")
        finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_percentage="0")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("70.00"))
        purchase = self.wallet.ledger_entries.get(entry_type=LedgerEntry.Type.PURCHASE)
        self.assertEqual(purchase.location, self.location_2)
        self.assertTrue(purchase.bill_number.startswith("B-"))

    def test_unverified_member_cannot_pay(self):
        self.customer.member_profile.email_verified = False
        self.customer.member_profile.save(update_fields=["email_verified"])
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="50", actor=self.owner)
        with self.assertRaises(ValidationError):
            create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="10")

    def test_staff_cannot_use_owner_permission(self):
        with self.assertRaises(PermissionDenied): require_role(self.staff, self.business, OWNER_ROLES)

    def test_purchase_cannot_make_balance_negative(self):
        with self.assertRaises(ValidationError): create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="1")


class TierTests(PlatformMixin, TestCase):
    def setUp(self): self.create_platform()

    def test_tier_is_based_on_monthly_topups(self):
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="499", actor=self.owner)
        self.wallet.refresh_from_db(); self.assertEqual(self.wallet.tier, Wallet.Tier.SILVER)
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="1", actor=self.owner)
        self.wallet.refresh_from_db(); self.assertEqual(self.wallet.tier, Wallet.Tier.GOLD); self.assertEqual(self.wallet.monthly_topup_total, Decimal("500.00"))
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="200", actor=self.owner)
        self.wallet.refresh_from_db(); self.assertEqual(self.wallet.tier, Wallet.Tier.PLATINUM); self.assertEqual(self.wallet.monthly_topup_total, Decimal("700.00"))


class PaymentConfirmationTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="200", actor=self.owner)

    def test_customer_confirms_payment_and_tip_is_separate(self):
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="40", description="Shisha")
        self.assertEqual(payment.status, PaymentRequest.Status.PENDING)
        payment = finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_percentage="10")
        payment.refresh_from_db(); self.wallet.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payment.tip_amount, Decimal("4.00"))
        self.assertEqual(self.wallet.balance, Decimal("156.00"))
        self.assertEqual(payment.ledger_entries.count(), 2)
        self.assertTrue(payment.ledger_entries.filter(entry_type=LedgerEntry.Type.PURCHASE).exists())
        self.assertTrue(payment.ledger_entries.filter(entry_type=LedgerEntry.Type.TIP).exists())
        self.assertEqual(AppNotification.objects.filter(recipient=self.owner).count(), 1)

    def test_only_wallet_owner_can_confirm(self):
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="10")
        with self.assertRaises(PermissionDenied): finalize_payment_request(payment=payment, confirmed_by=self.owner, tip_percentage="0")

    def test_invalid_tip_option_is_rejected(self):
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="10")
        with self.assertRaises(ValidationError): finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_percentage="7")

    def test_confirmation_can_be_disabled_by_owner(self):
        self.settings.require_customer_confirmation = False
        self.settings.save(update_fields=["require_customer_confirmation"])
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="10", tip_percentage="5")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payment.tip_amount, Decimal("0.50"))


@override_settings(DEFAULT_BUSINESS_SLUG="shisha-bar", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CustomerRegistrationTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="shisha-bar")
        BusinessSettings.objects.create(business=self.business)
        Location.objects.create(business=self.business, name="SAMS 1", slug="sams-1")
        LegalConfiguration.objects.create(business=self.business, app_display_name=self.business.name, controller_name=self.business.name)

    def registration_payload(self, email="new.member@example.com", birth_date="1995-05-05"):
        return {"first_name": "Lena", "last_name": "Sommer", "email": email, "phone": "+49 160 1234567", "birth_date": birth_date, "age_confirmed": "on", "password1": "SamsMember2026!", "password2": "SamsMember2026!", "accept_terms": "on", "acknowledge_privacy": "on"}

    def test_registration_requires_adult_birth_date(self):
        underage = date.today() - timedelta(days=17 * 365)
        response = self.client.post(reverse("register"), self.registration_payload(birth_date=underage.isoformat()))
        self.assertEqual(response.status_code, 200); self.assertContains(response, "erst ab 18 Jahren"); self.assertEqual(Wallet.objects.count(), 0)

    def test_registration_creates_unverified_profile_wallet_and_session(self):
        response = self.client.post(reverse("register"), self.registration_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("customer_dashboard"))
        user = get_user_model().objects.get(email="new.member@example.com")
        profile = user.member_profile; wallet = Wallet.objects.get(owner=user, business=self.business)
        self.assertFalse(profile.email_verified); self.assertTrue(profile.age_confirmed); self.assertEqual(profile.birth_date, date(1995, 5, 5)); self.assertEqual(wallet.display_name, "Lena Sommer")
        self.assertEqual(wallet.member_number, "101")
        self.assertTrue(LegalAcceptance.objects.filter(user=user, document_type=LegalAcceptance.DocumentType.TERMS).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        location_response = self.client.get(reverse("customer_dashboard"))
        self.assertRedirects(location_response, reverse("customer_location_select"))

    def test_email_verification_link_activates_member(self):
        self.client.post(reverse("register"), self.registration_payload())
        user = get_user_model().objects.get(email="new.member@example.com")
        response = self.client.get(reverse("verify_email", args=[_verification_token(user)]))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        user.member_profile.refresh_from_db(); self.assertTrue(user.member_profile.email_verified)

    def test_duplicate_email_is_rejected(self):
        get_user_model().objects.create_user(username="existing@example.com", email="existing@example.com", password="Existing2026!")
        response = self.client.post(reverse("register"), self.registration_payload("existing@example.com"))
        self.assertEqual(response.status_code, 200); self.assertContains(response, "besteht bereits ein Konto"); self.assertEqual(Wallet.objects.count(), 0)


class OfferTests(PlatformMixin, TestCase):
    def setUp(self): self.create_platform()
    def test_offers_filter_by_location_and_tier(self):
        Offer.objects.create(business=self.business, location=self.location_1, title="Nord Silver", body="Visible", target_tier=Offer.TargetTier.SILVER, created_by=self.owner)
        Offer.objects.create(business=self.business, location=self.location_2, title="Süd Silver", body="Hidden", target_tier=Offer.TargetTier.SILVER, created_by=self.owner)
        Offer.objects.create(business=self.business, title="Gold only", body="Hidden", target_tier=Offer.TargetTier.GOLD, created_by=self.owner)
        titles = set(active_offers_for(self.wallet, self.location_1).values_list("title", flat=True))
        self.assertEqual(titles, {"Nord Silver"})


class OwnerPermissionTests(PlatformMixin, TestCase):
    def setUp(self): self.create_platform()
    def test_staff_cannot_topup_through_api(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("api_manager_topup"), {"wallet_token": str(self.wallet.qr_token), "amount": "20.00"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)


class ManagerQrScanTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform(); self.other_business = Business.objects.create(name="Other Lounge", slug="other"); self.other_wallet = Wallet.objects.create(business=self.other_business, display_name="Other")
    def test_owner_scan_redirects_to_member_detail(self):
        self.client.force_login(self.owner); response = self.client.get(reverse("manager_wallet_scan"), {"token": str(self.wallet.qr_token)}); self.assertRedirects(response, reverse("manager_wallet_detail", args=[self.wallet.pk]))
    def test_owner_cannot_open_wallet_from_another_business_by_scan(self):
        self.client.force_login(self.owner); response = self.client.get(reverse("manager_wallet_scan"), {"token": str(self.other_wallet.qr_token)}); self.assertRedirects(response, reverse("manager_dashboard"))
    def test_staff_cannot_use_manager_scan(self):
        self.client.force_login(self.staff); response = self.client.get(reverse("manager_wallet_scan"), {"token": str(self.wallet.qr_token)}); self.assertEqual(response.status_code, 403)


class BillAccessTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform(); self.entry = post_wallet_entry(wallet=self.wallet, location=self.location_1, entry_type=LedgerEntry.Type.TOPUP, amount="50.00", actor=self.owner, description="Cash top-up")
    def test_customer_owner_and_staff_can_open_business_bill(self):
        for user in (self.customer, self.owner, self.staff):
            self.client.force_login(user); response = self.client.get(reverse("bill_detail", args=[self.entry.pk])); self.assertEqual(response.status_code, 200); self.assertContains(response, self.entry.bill_number)
    def test_unrelated_customer_cannot_open_bill(self):
        outsider = get_user_model().objects.create_user(username="outsider", password="test"); self.client.force_login(outsider); response = self.client.get(reverse("bill_detail", args=[self.entry.pk])); self.assertEqual(response.status_code, 403)
