import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .compliance_models import TestWalletMarker
from .compliance_qr import issue_wallet_qr, resolve_payment_qr
from .legal_models import LegalAcceptance, LegalConfiguration
from .models import AuditEvent, Business, LedgerEntry, Location, MemberProfile, Membership, PaymentRequest, Wallet
from .services import post_wallet_entry


@override_settings(
    DEFAULT_BUSINESS_SLUG="shisha-bar",
    WALLET_QR_MAX_AGE_SECONDS=90,
    WALLET_QR_REFRESH_SECONDS=45,
    ALLOW_TEST_DATA_PURGE=False,
)
class ComplianceHardeningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="Sams Club Lounge", slug="shisha-bar")
        LegalConfiguration.objects.create(
            business=self.business,
            controller_name="A+ Solution GmbH",
            controller_address="Teststraße 1, Frankfurt",
            contact_email="app@example.com",
            privacy_email="privacy@example.com",
        )
        self.location = Location.objects.create(
            business=self.business,
            name="SAMS Test",
            slug="sams-test",
            is_active=True,
        )
        self.customer = User.objects.create_user(
            username="member@example.com",
            email="member@example.com",
            password="Member-Test-2026!",
            first_name="Test",
            last_name="Member",
        )
        MemberProfile.objects.create(
            user=self.customer,
            age_confirmed=True,
            email_verified=True,
        )
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.customer,
            display_name="Test Member",
            email=self.customer.email,
        )
        for document_type in (
            LegalAcceptance.DocumentType.TERMS,
            LegalAcceptance.DocumentType.PRIVACY,
        ):
            LegalAcceptance.objects.create(
                user=self.customer,
                business=self.business,
                document_type=document_type,
                version="1.0",
                source=LegalAcceptance.Source.REGISTRATION,
                member_number=self.wallet.member_number,
            )
        self.owner = User.objects.create_user(
            username="owner-compliance",
            password="Owner-Test-2026!",
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
        )
        self.staff = User.objects.create_user(
            username="staff-compliance",
            password="Staff-Test-2026!",
        )
        Membership.objects.create(
            user=self.staff,
            business=self.business,
            role=Membership.Role.STAFF,
        )
        self.topup = post_wallet_entry(
            wallet=self.wallet,
            location=self.location,
            entry_type=LedgerEntry.Type.TOPUP,
            amount=Decimal("50.00"),
            actor=self.owner,
            description="Compliance test top-up",
        )

    def test_argon2_is_the_preferred_password_hasher(self):
        self.assertEqual(
            settings.PASSWORD_HASHERS[0],
            "django.contrib.auth.hashers.Argon2PasswordHasher",
        )

    def test_rotating_app_qr_and_static_apple_wallet_qr_resolve_for_payment(self):
        signed_token = issue_wallet_qr(self.wallet)
        self.assertTrue(signed_token.startswith("samsqr1."))
        self.assertEqual(resolve_payment_qr(signed_token, business=self.business), self.wallet)
        self.assertEqual(resolve_payment_qr(str(self.wallet.qr_token), business=self.business), self.wallet)

    def test_wallet_api_never_exposes_the_static_database_qr_uuid(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("api_wallet"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["qr_token"].startswith("samsqr1."))
        self.assertNotEqual(response.json()["qr_token"], str(self.wallet.qr_token))

    def test_profile_api_never_exposes_the_static_database_qr_uuid(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("api_me"))
        self.assertEqual(response.status_code, 200)
        wallet_payload = response.json()["customer_wallets"][0]
        self.assertTrue(wallet_payload["qr_token"].startswith("samsqr1."))
        self.assertNotEqual(wallet_payload["qr_token"], str(self.wallet.qr_token))

    def test_staff_payment_accepts_both_qr_types_and_staff_tip_is_authoritative(self):
        self.client.force_login(self.staff)
        payload = {
            "wallet_token": str(self.wallet.qr_token),
            "location_id": str(self.location.pk),
            "amount": "5.00",
            "tip_amount": "2.00",
        }
        response = self.client.post(reverse("staff_charge"), payload)
        self.assertEqual(response.status_code, 302)

        payload["wallet_token"] = issue_wallet_qr(self.wallet)
        response = self.client.post(reverse("staff_charge"), payload)
        self.assertEqual(response.status_code, 302)

        payments = PaymentRequest.objects.filter(wallet=self.wallet).order_by("created_at")
        self.assertEqual(payments.count(), 2)
        self.assertTrue(all(payment.status == PaymentRequest.Status.PENDING for payment in payments))
        self.assertTrue(all(payment.customer_confirmation_required for payment in payments))
        self.assertTrue(all(payment.tip_selected_amount == Decimal("2.00") for payment in payments))
        self.assertEqual(
            LedgerEntry.objects.filter(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE).count(),
            0,
        )

        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("customer_confirm_payment", args=[payments.first().pk]),
            {"tip_amount": "9.00"},
        )
        self.assertEqual(response.status_code, 302)
        payments.first().refresh_from_db()
        self.assertEqual(payments.first().status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payments.first().tip_amount, Decimal("2.00"))
        self.assertEqual(
            LedgerEntry.objects.filter(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE).count(),
            1,
        )
        self.assertEqual(
            LedgerEntry.objects.filter(wallet=self.wallet, entry_type=LedgerEntry.Type.TIP).count(),
            1,
        )

    def test_financial_hard_delete_is_denied_for_production_wallets(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("manager_clear_wallet_history", args=[self.wallet.pk]),
            {"confirmation": "LÖSCHEN"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LedgerEntry.objects.filter(pk=self.topup.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                action="financial_hard_delete_denied",
                object_id=str(self.wallet.pk),
            ).exists()
        )

    @override_settings(ALLOW_TEST_DATA_PURGE=True)
    def test_explicitly_marked_test_wallet_can_be_purged_only_in_test_mode(self):
        TestWalletMarker.objects.create(
            wallet=self.wallet,
            reason="Automated compliance test",
            marked_by=self.owner,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("manager_clear_wallet_history", args=[self.wallet.pk]),
            {"confirmation": "LÖSCHEN"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LedgerEntry.objects.filter(wallet=self.wallet).exists())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="test_wallet_history_purged",
                object_id=str(self.wallet.pk),
            ).exists()
        )

    def test_customer_can_export_personal_data_and_export_is_audited(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("customer_data_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["account"]["email"], self.customer.email)
        self.assertEqual(payload["wallet"]["member_number"], self.wallet.member_number)
        self.assertGreaterEqual(len(payload["ledger_entries"]), 1)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="gdpr_data_export",
                object_id=str(self.wallet.pk),
            ).exists()
        )

    def test_destructive_tools_are_hidden_in_normal_production_mode(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_wallet_detail", args=[self.wallet.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Testdaten bereinigen")
