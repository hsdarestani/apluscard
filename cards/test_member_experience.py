from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .experience_models import LocationVisual, TransactionCase
from .experience_services import create_transaction_case
from .models import AppNotification, Business, LedgerEntry, Location, MemberProfile, Membership, Offer, ReviewStatus, Wallet
from .services import post_wallet_entry
from .wallet_pass import _pass_files

User = get_user_model()


class MemberExperienceMixin:
    def create_experience(self):
        self.business = Business.objects.create(name="SAMS", slug="sams")
        self.location = Location.objects.create(business=self.business, name="SAMS Club Lounge", slug="sams-club-lounge", address="Hanauer Landstraße 99", google_review_url="https://g.page/r/test")
        LocationVisual.objects.create(location=self.location, headline="Deine Lounge", description="Nachtleben in Frankfurt", sort_order=1)
        self.owner = User.objects.create_user(username="owner-exp", password="owner-secret")
        self.manager = User.objects.create_user(username="manager-exp", password="manager-secret")
        self.staff = User.objects.create_user(username="staff-exp", password="staff-secret")
        self.other_staff = User.objects.create_user(username="other-staff-exp", password="other-staff-secret")
        self.customer = User.objects.create_user(username="customer-exp", password="customer-secret")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER, active=True)
        Membership.objects.create(user=self.manager, business=self.business, role=Membership.Role.MANAGER, active=True)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF, active=True)
        Membership.objects.create(user=self.other_staff, business=self.business, role=Membership.Role.STAFF, active=True)
        MemberProfile.objects.create(user=self.customer, phone="01710000000", birth_date=date.today() - timedelta(days=25 * 365), email_verified_at=date.today())
        self.wallet = Wallet.objects.create(owner=self.customer, business=self.business, member_number="101", balance=Decimal("100.00"))
        self.entry = post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount=Decimal("-30.00"), actor=self.staff, location=self.location, description="Testkauf")


class LocationSelectionTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()
    def test_customer_must_choose_visual_location_before_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("customer_dashboard"))
        self.assertRedirects(response, reverse("customer_location_select") + "?next=/customer/")
        selection = self.client.get(response.url)
        self.assertContains(selection, "Deine Lounge")
        post_response = self.client.post(reverse("customer_location_select"), {"location_id": self.location.id, "next": reverse("customer_dashboard")})
        self.assertRedirects(post_response, reverse("customer_dashboard"))
        dashboard = self.client.get(reverse("customer_dashboard"))
        self.assertContains(dashboard, self.location.name)
    def test_customer_qr_is_rendered_server_side_without_qrcode_library(self):
        self.client.force_login(self.customer)
        session = self.client.session
        session["active_location_id"] = str(self.location.id)
        session.save()
        response = self.client.get(reverse("customer_dashboard"))
        self.assertContains(response, "qr-image")
        self.assertContains(response, "data:image/png;base64,")
        self.assertNotContains(response, "cdnjs.cloudflare.com/ajax/libs/qrcodejs")


class InAppNotificationTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()
    def test_financial_flow_notifies_each_relevant_role(self):
        self.assertTrue(AppNotification.objects.filter(recipient=self.customer, kind=AppNotification.Kind.PAYMENT).exists())
        self.assertTrue(AppNotification.objects.filter(recipient=self.owner, kind=AppNotification.Kind.PAYMENT).exists())
        self.assertTrue(AppNotification.objects.filter(recipient=self.manager, kind=AppNotification.Kind.PAYMENT).exists())
    def test_new_offer_notifies_matching_customer(self):
        Offer.objects.create(business=self.business, title="VIP Bonus", description="Nur heute", active=True, target_tier=Offer.TargetTier.ALL)
        self.assertTrue(AppNotification.objects.filter(recipient=self.customer, kind=AppNotification.Kind.OFFER, title="VIP Bonus").exists())


class TransactionCaseTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()
    def test_customer_can_create_case_for_own_transaction(self):
        transaction_case = create_transaction_case(entry=self.entry, opened_by=self.customer, reason=TransactionCase.Reason.WRONG_AMOUNT, description="Der Betrag ist falsch.", requested_amount="20")
        self.assertEqual(transaction_case.opened_by_role, TransactionCase.OpenedByRole.CUSTOMER)
        self.assertEqual(transaction_case.status, TransactionCase.Status.OPEN)
        self.assertEqual(transaction_case.case_number[:4], "TF-2")
    def test_staff_can_report_own_transaction_but_unrelated_staff_cannot(self):
        staff_case = create_transaction_case(entry=self.entry, opened_by=self.staff, reason=TransactionCase.Reason.WRONG_MEMBER, description="Ich habe versehentlich die falsche Mitgliedskarte belastet.", requested_amount="30")
        self.assertEqual(staff_case.opened_by_role, TransactionCase.OpenedByRole.STAFF)
        with self.assertRaises(PermissionDenied):
            create_transaction_case(entry=self.entry, opened_by=self.other_staff, reason=TransactionCase.Reason.OTHER, description="Nicht meine Transaktion und daher nicht erlaubt.")

    def test_management_can_open_case_for_any_business_transaction(self):
        management_case = create_transaction_case(entry=self.entry, opened_by=self.manager, reason=TransactionCase.Reason.OTHER, description="Interne Kassenprüfung durch die Verwaltung.")
        self.assertEqual(management_case.opened_by_role, TransactionCase.OpenedByRole.MANAGEMENT)

    def test_transaction_page_shows_ledger_entry_without_existing_case(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transaction_cases"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.entry.bill_number)
        self.assertContains(response, "Prüffall anlegen")


class SecurityAndPerformanceTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()
    def test_security_headers_hide_framework_hints_and_restrict_browser(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("X-Powered-By", response)
    def test_service_worker_caches_sams_release_assets(self):
        response = self.client.get(reverse("service_worker"))
        content = response.content.decode("utf-8")
        self.assertIn("sams-club-lounge-v13", content)
        self.assertIn("/static/cards/push.css", content)
        self.assertIn("/app-icon-512.png?v=scl-20260725", content)
        self.assertIn("const isAsset", content)
        self.assertNotIn("caches.match('/')", content)
    def test_low_power_mode_is_in_client_bundle(self):
        content = (Path(settings.BASE_DIR) / "cards" / "static" / "cards" / "app.js").read_text(encoding="utf-8")
        self.assertIn("low-power", content)
        self.assertIn("visibilitychange", content)


class AppleWalletPayloadTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()
    @override_settings(APPLE_WALLET_PASS_TYPE_ID="pass.de.sams.member", APPLE_WALLET_TEAM_ID="TEAM123456")
    def test_store_card_payload_contains_member_number_and_qr(self):
        request = RequestFactory().get("/customer/apple-wallet/", HTTP_HOST="cards.smarbiz.sbs", secure=True)
        files = _pass_files(self.wallet, request)
        payload = json.loads(files["pass.json"])
        self.assertEqual(payload["storeCard"]["primaryFields"][0]["value"], "101")
        self.assertEqual(payload["barcodes"][0]["format"], "PKBarcodeFormatQR")
        self.assertEqual(payload["barcodes"][0]["message"], str(self.wallet.qr_token))
        self.assertIn("icon.png", files)
        self.assertIn("logo.png", files)
