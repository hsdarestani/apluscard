import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .experience_models import TransactionCase
from .experience_services import create_transaction_case, review_transaction_case
from .legal_models import LegalAcceptance, LegalConfiguration
from .models import AppNotification, Business, BusinessSettings, LedgerEntry, Location, MemberProfile, Membership, Offer, Wallet
from .services import create_payment_request, finalize_payment_request, post_wallet_entry
from .wallet_pass import _pass_files


class MemberExperienceMixin:
    def create_experience(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="shisha-bar")
        self.settings = BusinessSettings.objects.create(business=self.business)
        self.location_1 = Location.objects.create(business=self.business, name="Sams Club Lounge", slug="sams-club-lounge", address="Frankfurter Straße 198\n61118 Bad Vilbel\nTelefon: 06101/5969952", position=1)
        self.location_2 = Location.objects.create(business=self.business, name="Sams Club Lounge CITY", slug="sams-club-lounge-city", address="Frankfurter Straße 38\n61118 Bad Vilbel\nTelefon: 06101/5969440", position=2)
        self.location_3 = Location.objects.create(business=self.business, name="DIMA Sportsbar", slug="dima-sportsbar", address="Frankfurter Straße 36\n61118 Bad Vilbel\nTelefon: 06101/5969440", position=3)
        self.owner = User.objects.create_user(username="owner-x", password="test")
        self.manager = User.objects.create_user(username="manager-x", password="test")
        self.staff = User.objects.create_user(username="staff-x", password="test")
        self.other_staff = User.objects.create_user(username="other-staff-x", password="test")
        self.customer = User.objects.create_user(username="member-x@example.com", email="member-x@example.com", password="test", first_name="Mia", last_name="Member")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.manager, business=self.business, role=Membership.Role.MANAGER)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        Membership.objects.create(user=self.other_staff, business=self.business, role=Membership.Role.STAFF)
        MemberProfile.objects.create(user=self.customer, birth_date=date(1990, 1, 1), age_confirmed=True, email_verified=True, email_verified_at=timezone.now())
        self.wallet = Wallet.objects.create(business=self.business, owner=self.customer, display_name="Mia Member", email=self.customer.email)
        LegalConfiguration.objects.create(business=self.business, app_display_name=self.business.name, controller_name=self.business.name, terms_version="1.0", privacy_version="1.0")
        for document_type in (LegalAcceptance.DocumentType.TERMS, LegalAcceptance.DocumentType.PRIVACY):
            LegalAcceptance.objects.create(user=self.customer, business=self.business, document_type=document_type, version="1.0", source=LegalAcceptance.Source.REGISTRATION, email_hash="test", member_number=self.wallet.member_number)

    def select_customer_location(self):
        session = self.client.session
        session["active_location_id"] = str(self.location_1.pk)
        session.save()


class SequentialMemberNumberTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()

    def test_numbers_start_at_101_and_continue_without_random_digits(self):
        second = Wallet.objects.create(business=self.business, display_name="Zweites Mitglied")
        third = Wallet.objects.create(business=self.business, display_name="Drittes Mitglied")
        self.assertEqual([self.wallet.member_number, second.member_number, third.member_number], ["101", "102", "103"])


class LocationSelectionTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience(); self.client.force_login(self.customer)

    def test_customer_must_choose_visual_location_before_dashboard(self):
        response = self.client.get(reverse("customer_dashboard"))
        self.assertRedirects(response, reverse("customer_location_select"))
        chooser = self.client.get(reverse("customer_location_select"))
        self.assertEqual(chooser.status_code, 200)
        self.assertContains(chooser, "Wo möchtest du")
        self.assertContains(chooser, "DIMA Sportsbar")
        selected = self.client.post(reverse("customer_location_select"), {"location_id": self.location_2.pk, "next": reverse("customer_dashboard")})
        self.assertRedirects(selected, reverse("customer_dashboard"))
        self.assertEqual(self.client.session["active_location_id"], str(self.location_2.pk))
        self.assertEqual(self.client.get(reverse("customer_dashboard")).status_code, 200)

    def test_customer_qr_is_rendered_server_side_without_qrcode_library(self):
        self.select_customer_location()
        response = self.client.get(reverse("customer_dashboard"))
        self.assertContains(response, "data:image/png;base64,")
        self.assertNotContains(response, "qrcode.min.js")
        self.assertNotContains(response, "new QRCode")


class InAppNotificationTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()

    def test_financial_flow_notifies_each_relevant_role(self):
        post_wallet_entry(wallet=self.wallet, location=self.location_1, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)
        self.assertTrue(AppNotification.objects.filter(recipient=self.customer, title="Guthaben aufgeladen").exists())
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="20")
        self.assertTrue(AppNotification.objects.filter(recipient=self.customer, title="Zahlung wartet auf Bestätigung").exists())
        payment = finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_percentage="0")
        for user in (self.customer, self.staff, self.owner, self.manager):
            self.assertTrue(AppNotification.objects.filter(recipient=user, title="A+ Pay Zahlung abgeschlossen").exists())

    def test_new_offer_notifies_matching_customer(self):
        Offer.objects.create(business=self.business, location=self.location_1, title="Heute für Silber", body="Nur heute verfügbar", target_tier=Offer.TargetTier.SILVER, created_by=self.owner)
        self.assertTrue(AppNotification.objects.filter(recipient=self.customer, kind=AppNotification.Kind.OFFER, title="Heute für Silber").exists())


class TransactionCaseTests(MemberExperienceMixin, TestCase):
    def setUp(self):
        self.create_experience()
        post_wallet_entry(wallet=self.wallet, location=self.location_1, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)
        payment = create_payment_request(wallet=self.wallet, location=self.location_1, actor=self.staff, amount="30")
        self.payment = finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_percentage="0")
        self.entry = self.payment.purchase_entry

    def test_customer_case_owner_approval_creates_single_auditable_refund(self):
        transaction_case = create_transaction_case(entry=self.entry, opened_by=self.customer, reason=TransactionCase.Reason.WRONG_AMOUNT, description="Der angezeigte Betrag war zehn Euro zu hoch.", requested_amount="10")
        self.assertEqual(transaction_case.status, TransactionCase.Status.OPEN)
        self.assertTrue(AppNotification.objects.filter(recipient=self.owner, title="Neuer Transaktionsfall").exists())
        reviewed = review_transaction_case(transaction_case=transaction_case, reviewer=self.owner, action=TransactionCase.Status.APPROVED, manager_note="Kassenfehler bestätigt.", approved_amount="10")
        self.wallet.refresh_from_db()
        self.assertEqual(reviewed.status, TransactionCase.Status.APPROVED)
        self.assertEqual(self.wallet.balance, Decimal("80.00"))
        self.assertIsNotNone(reviewed.refund_entry_id)
        self.assertEqual(reviewed.refund_entry.entry_type, LedgerEntry.Type.REFUND)
        with self.assertRaises(ValidationError):
            review_transaction_case(transaction_case=reviewed, reviewer=self.owner, action=TransactionCase.Status.APPROVED, approved_amount="10")

    def test_manager_can_review_but_only_owner_can_approve_refund(self):
        transaction_case = create_transaction_case(entry=self.entry, opened_by=self.customer, reason=TransactionCase.Reason.DUPLICATE, description="Diese Zahlung wurde meiner Ansicht nach doppelt gebucht.", requested_amount="30")
        with self.assertRaises(PermissionDenied):
            review_transaction_case(transaction_case=transaction_case, reviewer=self.manager, action=TransactionCase.Status.APPROVED, approved_amount="30")
        reviewed = review_transaction_case(transaction_case=transaction_case, reviewer=self.manager, action=TransactionCase.Status.IN_REVIEW, manager_note="Kassenjournal wird geprüft.")
        self.assertEqual(reviewed.status, TransactionCase.Status.IN_REVIEW)

    def test_staff_can_report_own_transaction_but_unrelated_staff_cannot(self):
        staff_case = create_transaction_case(entry=self.entry, opened_by=self.staff, reason=TransactionCase.Reason.WRONG_MEMBER, description="Ich habe versehentlich die falsche Mitgliedskarte belastet.", requested_amount="30")
        self.assertEqual(staff_case.opened_by_role, TransactionCase.OpenedByRole.STAFF)
        with self.assertRaises(PermissionDenied):
            create_transaction_case(entry=self.entry, opened_by=self.other_staff, reason=TransactionCase.Reason.OTHER, description="Nicht meine Transaktion und daher nicht erlaubt.")


class SecurityAndPerformanceTests(MemberExperienceMixin, TestCase):
    def setUp(self): self.create_experience()

    def test_security_headers_hide_framework_hints_and_restrict_browser(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("X-Powered-By", response)

    def test_service_worker_only_caches_static_assets(self):
        response = self.client.get(reverse("service_worker"))
        content = response.content.decode("utf-8")
        self.assertIn("sams-lounge-v8", content)
        self.assertIn("const isAsset", content)
        self.assertNotIn("caches.match('/')", content)

    def test_low_power_mode_is_in_client_bundle(self):
        response = self.client.get("/static/cards/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"low-power", response.content)
        self.assertIn(b"visibilitychange", response.content)


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
