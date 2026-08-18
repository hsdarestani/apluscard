from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .emailing import send_verification_email
from .forms import OfferForm
from .models import BusinessSettings, LedgerEntry, PaymentRequest
from .services import create_payment_request, post_wallet_entry
from .tests import PlatformMixin


class PaymentAndOwnerFlowTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)

    def test_customer_confirmation_is_disabled_by_default(self):
        self.assertFalse(BusinessSettings.objects.get(business=self.business).require_customer_confirmation)

    def test_owner_can_directly_charge_member_with_fixed_euro_tip(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("manager_charge", args=[self.wallet.pk]),
            {
                "location_id": str(self.location_1.pk),
                "amount": "20.00",
                "tip_amount": "2.00",
                "description": "Testbestellung",
                "order_reference": "TEST-20",
            },
        )
        self.assertRedirects(response, reverse("manager_wallet_detail", args=[self.wallet.pk]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("78.00"))
        payment = PaymentRequest.objects.get(wallet=self.wallet)
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payment.tip_amount, Decimal("2.00"))
        self.assertTrue(self.wallet.ledger_entries.filter(entry_type=LedgerEntry.Type.PURCHASE, amount=Decimal("-20.00")).exists())
        self.assertTrue(self.wallet.ledger_entries.filter(entry_type=LedgerEntry.Type.TIP, amount=Decimal("-2.00")).exists())

    def test_manager_wallet_page_explains_charge_topup_and_refund(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_wallet_detail", args=[self.wallet.pk]))
        self.assertContains(response, "Zahlung abbuchen")
        self.assertContains(response, "Prepaid-Guthaben")
        self.assertContains(response, "Betrag zurückgeben")


class StaffTransactionSuccessPopupTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="100", actor=self.owner)

    def test_staff_dashboard_contains_direct_success_popup_without_customer_confirmation_wait(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertContains(response, 'id="transaction-success-popover"', html=False)
        self.assertContains(response, "Zahlung jetzt abbuchen")
        self.assertContains(response, "keine Bestätigung erforderlich")
        self.assertContains(response, "payload.status!=='CONFIRMED'", html=False)
        self.assertContains(response, "Transaktion abgeschlossen")
        self.assertNotContains(response, "Warte auf Bestätigung")
        self.assertNotContains(response, "startPaymentWatch", html=False)

    def test_staff_api_charge_is_immediate_even_if_business_confirmation_is_enabled(self):
        self.settings.require_customer_confirmation = True
        self.settings.save(update_fields=["require_customer_confirmation"])

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("api_staff_charge"),
            {
                "wallet_token": str(self.wallet.qr_token),
                "location_id": str(self.location_1.pk),
                "amount": "12.50",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], PaymentRequest.Status.CONFIRMED)
        self.assertEqual(Decimal(payload["base_amount"]), Decimal("12.50"))
        self.assertEqual(Decimal(payload["tip_amount"]), Decimal("0.00"))

        payment = PaymentRequest.objects.get(pk=payload["id"])
        self.assertFalse(payment.customer_confirmation_required)
        self.assertIsNotNone(payment.confirmed_at)
        self.assertIsNotNone(payment.purchase_entry_id)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("87.50"))
        self.assertFalse(PaymentRequest.objects.filter(wallet=self.wallet, status=PaymentRequest.Status.PENDING).exists())

    def test_staff_form_fallback_also_books_immediately(self):
        self.settings.require_customer_confirmation = True
        self.settings.save(update_fields=["require_customer_confirmation"])

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("staff_charge"),
            {
                "wallet_token": self.wallet.member_number,
                "location_id": str(self.location_1.pk),
                "amount": "8.00",
            },
        )

        self.assertRedirects(response, reverse("staff_dashboard"))
        payment = PaymentRequest.objects.get(wallet=self.wallet)
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertFalse(payment.customer_confirmation_required)
        self.assertEqual(payment.tip_amount, Decimal("0.00"))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("92.00"))

    def test_payment_status_is_only_visible_to_staff_member_who_created_it(self):
        payment = create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.staff,
            amount="12.50",
            tip_amount="0.00",
            customer_tip_required=False,
            force_immediate=True,
        )
        status_url = reverse("api_staff_payment_status", args=[payment.pk])

        self.client.force_login(self.staff)
        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], PaymentRequest.Status.CONFIRMED)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(status_url).status_code, 404)


class OfferAndMobileUiTests(PlatformMixin, TestCase):
    def setUp(self): self.create_platform()

    def test_offer_begin_and_end_are_visible_datetime_inputs(self):
        form = OfferForm(business=self.business)
        self.assertEqual(form.fields["starts_at"].widget.input_type, "datetime-local")
        self.assertEqual(form.fields["ends_at"].widget.input_type, "datetime-local")
        self.assertFalse(form.fields["starts_at"].widget.is_hidden)
        self.assertFalse(form.fields["ends_at"].widget.is_hidden)

    def test_mobile_navigation_uses_svg_icons(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_dashboard"))
        self.assertContains(response, '<nav class="mobile-nav mobile-nav-management"', html=False)
        self.assertContains(response, '<span>Inhalte</span>', html=False)
        self.assertContains(response, '<svg viewBox="0 0 24 24"', count=5, html=False)
        self.assertNotContains(response, "⌂")

    def test_polished_checkbox_and_tip_styles_are_present(self):
        css = (Path(settings.BASE_DIR) / "cards" / "static" / "cards" / "ui-fixes.css").read_text(encoding="utf-8")
        self.assertIn('input[type="checkbox"]', css)
        self.assertIn("appearance: none", css)
        self.assertIn(".tip-radio-grid", css)
        self.assertIn(".mobile-nav svg", css)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    APP_NAME="A+ Card",
    APP_PUBLISHER="A+Solution GmbH",
    DEFAULT_FROM_EMAIL="A+ Card <app@aplus-solution.de>",
    EMAIL_REPLY_TO="app@aplus-solution.de",
)
class EmailDeliveryTests(PlatformMixin, TestCase):
    def setUp(self): self.create_platform()

    def test_verification_email_uses_aplus_sender_and_contains_link(self):
        request = RequestFactory().get("/", HTTP_HOST="app.samsclublounge.de", secure=True)
        sent = send_verification_email(request, self.customer)
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "A+ Card <app@aplus-solution.de>")
        self.assertEqual(mail.outbox[0].reply_to, ["app@aplus-solution.de"])
        self.assertIn("A+Solution GmbH", mail.outbox[0].body)
        self.assertIn("https://cards.smarbiz.sbs/accounts/verify/", mail.outbox[0].body)
