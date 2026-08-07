from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import CustomerRegistrationForm
from .models import AppNotification, Business, BusinessSettings, Location, Membership, Wallet
from .push_models import PushDelivery


@override_settings(DEFAULT_BUSINESS_SLUG="shisha-bar")
class RegistrationOwnerNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS CLUB LOUNGE", slug="shisha-bar")
        BusinessSettings.objects.create(business=self.business)
        Location.objects.create(business=self.business, name="SAMS 1", slug="sams-1")
        self.owner = User.objects.create_user(username="owner-registration-test", password="test")
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
            is_active=True,
        )

    def _registration_form(self):
        return CustomerRegistrationForm(
            data={
                "first_name": "Lena",
                "last_name": "Sommer",
                "email": "lena.sommer@example.com",
                "phone": "+49 160 1234567",
                "birth_date": "1995-05-05",
                "age_confirmed": "on",
                "password1": "SamsMember2026!",
                "password2": "SamsMember2026!",
            }
        )

    def test_self_registration_notifies_owner_and_queues_native_push(self):
        form = self._registration_form()
        self.assertTrue(form.is_valid(), form.errors.as_json())

        with self.captureOnCommitCallbacks(execute=True):
            user = form.save()
            wallet = Wallet.objects.create(
                business=self.business,
                owner=user,
                display_name="Lena Sommer",
                phone=form.cleaned_data["phone"],
                email=user.email,
            )

        notification = AppNotification.objects.get(
            recipient=self.owner,
            title="Neues Mitglied registriert",
        )
        self.assertIn("Lena Sommer", notification.body)
        self.assertIn(wallet.member_number, notification.body)
        self.assertEqual(notification.data["member_number"], wallet.member_number)
        self.assertEqual(
            notification.data["url"],
            reverse("manager_wallet_detail", args=[wallet.pk]),
        )
        self.assertTrue(PushDelivery.objects.filter(notification=notification).exists())

    def test_staff_created_card_does_not_trigger_registration_push(self):
        Wallet.objects.create(business=self.business, display_name="Manuell angelegt")
        self.assertFalse(AppNotification.objects.filter(recipient=self.owner).exists())

    def test_owner_can_find_new_member_by_member_number(self):
        form = self._registration_form()
        self.assertTrue(form.is_valid(), form.errors.as_json())
        user = form.save()
        wallet = Wallet.objects.create(
            business=self.business,
            owner=user,
            display_name="Lena Sommer",
            phone=form.cleaned_data["phone"],
            email=user.email,
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_dashboard"), {"q": wallet.member_number})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lena Sommer")
        self.assertContains(response, f"Mitgliedsnummer {wallet.member_number}")
