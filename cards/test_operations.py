from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .compliance_qr import issue_wallet_qr
from .models import AppNotification, Business, BusinessSettings, Location, MemberProfile, Membership, PaymentRequest, PushDevice, Wallet
from .push_models import PushDelivery


class OperationsFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="shisha-bar")
        BusinessSettings.objects.create(business=self.business)
        self.location = Location.objects.create(business=self.business, name="SAMS", slug="sams", is_active=True)
        self.owner = User.objects.create_user(username="owner-op", password="test")
        self.manager = User.objects.create_user(username="manager-op", password="test")
        self.staff = User.objects.create_user(username="staff-op", password="test")
        self.customer = User.objects.create_user(username="member-op@example.com", email="member-op@example.com", password="test")
        Membership.objects.create(user=self.owner, business=self.business, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.manager, business=self.business, role=Membership.Role.MANAGER, can_manage_content=True)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        MemberProfile.objects.create(
            user=self.customer,
            birth_date=date(1990, 1, 1),
            age_confirmed=True,
            email_verified=True,
            email_verified_at=timezone.now(),
        )
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.customer,
            display_name="Test Member",
            email=self.customer.email,
            balance=Decimal("100.00"),
        )

    def test_staff_invalid_card_redirects_with_message_instead_of_404(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("staff_charge"),
            {
                "wallet_token": "not-a-card",
                "location_id": self.location.pk,
                "amount": "10.00",
            },
        )
        self.assertRedirects(response, reverse("staff_dashboard"))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    def test_completed_staff_payment_notifies_customer_and_management_and_queues_push(self):
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("staff_charge"),
                {
                    "wallet_token": issue_wallet_qr(self.wallet),
                    "location_id": self.location.pk,
                    "amount": "20.00",
                },
            )
        self.assertRedirects(response, reverse("staff_dashboard"))
        payment = PaymentRequest.objects.get(wallet=self.wallet)
        self.assertEqual(payment.status, PaymentRequest.Status.PENDING)
        self.assertTrue(payment.customer_confirmation_required)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

        self.client.force_login(self.customer)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("customer_confirm_payment", args=[payment.pk]),
                {"tip_amount": "0.00"},
            )
        self.assertRedirects(response, reverse("customer_dashboard"), fetch_redirect_response=False)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("80.00"))
        for user in (self.customer, self.staff, self.owner, self.manager):
            notification = AppNotification.objects.filter(recipient=user, title="A+ Pay Zahlung abgeschlossen").first()
            self.assertIsNotNone(notification)
            self.assertTrue(PushDelivery.objects.filter(notification=notification).exists())

    def test_owner_charge_notifies_owner_and_customer(self):
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("manager_charge", args=[self.wallet.pk]),
                {
                    "location_id": self.location.pk,
                    "amount": "15.00",
                    "tip_amount": "0.00",
                    "description": "Owner test",
                    "order_reference": "OWNER-1",
                },
            )
        self.assertRedirects(response, reverse("manager_wallet_detail", args=[self.wallet.pk]))
        for user in (self.owner, self.manager, self.customer):
            notification = AppNotification.objects.filter(recipient=user, title="A+ Pay Zahlung abgeschlossen").first()
            self.assertIsNotNone(notification)
            self.assertTrue(PushDelivery.objects.filter(notification=notification).exists())

    def test_management_privacy_choice_link_redirects_safely(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("privacy_choices"))
        self.assertRedirects(response, reverse("manager_dashboard"))

    def test_broadcast_and_direct_notifications_are_created_and_queued(self):
        self.client.force_login(self.manager)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("manager_broadcast_notification"),
                {"title": "Heute geöffnet", "body": "Wir freuen uns auf dich.", "target": "ALL", "kind": "SYSTEM"},
            )
        self.assertRedirects(response, reverse("manager_settings"))
        broadcast = AppNotification.objects.get(recipient=self.customer, title="Heute geöffnet")
        self.assertTrue(PushDelivery.objects.filter(notification=broadcast).exists())

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("manager_direct_notification", args=[self.wallet.pk]),
                {"title": "Nur für dich", "body": "Deine Reservierung ist bestätigt.", "kind": "SYSTEM"},
            )
        self.assertRedirects(response, reverse("manager_wallet_detail", args=[self.wallet.pk]))
        direct = AppNotification.objects.get(recipient=self.customer, title="Nur für dich")
        self.assertTrue(PushDelivery.objects.filter(notification=direct).exists())
