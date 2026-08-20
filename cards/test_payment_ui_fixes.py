from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .emailing import send_verification_email
from .forms import OfferForm
from .models import BusinessSettings, LedgerEntry, PaymentRequest
from .services import create_payment_request, finalize_payment_request, post_wallet_entry
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

    def test_staff_dashboard_contains_confirmed_transaction_popup_and_status_watch(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertContains(response, 'id="transaction-success-popover"', html=False)
        self.assertContains(response, "api/v1/staff/payments/", html=False)
        self.assertContains(response, "payload.status==='CONFIRMED'", html=False)
        self.assertContains(response, "Transaktion abgeschlossen")
        self.assertContains(response, 'name="tip_amount"', html=False)
        self.assertContains(response, "Trinkgeld wird vom Staff eingetragen")

    def test_payment_status_is_only_visible_to_staff_member_who_created_it(self):
        payment = create_payment_request(
            wallet=self.wallet,
            location=self.location_1,
            actor=self.staff,
            amount="12.50",
            tip_amount="2.50",
            customer_confirmation_required=True,
        )
        status_url = reverse("api_staff_payment_status", args=[payment.pk])

        self.client.force_login(self.staff)
        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], PaymentRequest.Status.PENDING)
        self.assertEqual(Decimal(response.json()["tip_selected_amount"]), Decimal("2.50"))

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(status_url).status_code, 404)

        # A customer cannot overwrite the tip prepared by staff.
        finalize_payment_request(payment=payment, confirmed_by=self.customer, tip_amount="9.99")
        self.client.force_login(self.staff)
        response = self.client.get(status_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], PaymentRequest.Status.CONFIRMED)
        self.assertEqual(Decimal(response.json()["tip_amount"]), Decimal("2.50"))
        self.assertEqual(Decimal(response.json()["total_amount"]), Decimal("15.00"))


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
