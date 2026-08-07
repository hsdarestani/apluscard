import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Business, Membership
from .services import MANAGER_ROLES, OWNER_ROLES, STAFF_ROLES, require_role


@mock.patch.dict(os.environ, {"PRIVILEGED_MFA_REQUIRED": "0"}, clear=False)
class OwnerAdminSeparationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS", slug="shisha-bar")
        self.owner = User.objects.create_user(
            username="sams-owner",
            password="Owner-Test-2026!",
            is_staff=False,
            is_superuser=False,
        )
        self.membership = Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
            is_active=True,
        )
        self.technical_admin = User.objects.create_superuser(
            username="aplus-admin",
            email="",
            password="Technical-Test-2026!",
        )

    def test_business_owner_keeps_all_business_roles_without_django_admin_flags(self):
        self.assertEqual(require_role(self.owner, self.business, OWNER_ROLES), self.membership)
        self.assertEqual(require_role(self.owner, self.business, MANAGER_ROLES), self.membership)
        self.assertEqual(require_role(self.owner, self.business, STAFF_ROLES), self.membership)
        self.assertFalse(self.owner.is_staff)
        self.assertFalse(self.owner.is_superuser)

    def test_business_owner_cannot_open_django_admin(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)

    def test_technical_superuser_has_admin_but_no_business_membership(self):
        self.assertFalse(Membership.objects.filter(user=self.technical_admin).exists())
        self.client.force_login(self.technical_admin)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
