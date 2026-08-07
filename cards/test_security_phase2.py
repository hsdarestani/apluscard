import io
import os
from unittest import mock

import pyotp
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from .models import AuditEvent, Business, BusinessSettings, Membership
from .security_models import AuditChainSeal, PrivilegedMfaDevice


@mock.patch.dict(
    os.environ,
    {
        "PRIVILEGED_MFA_REQUIRED": "1",
        "MFA_ENCRYPTION_KEY": "test-only-independent-mfa-encryption-key-2026",
    },
    clear=False,
)
class PrivilegedSecurityPhaseTwoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.business = Business.objects.create(name="SAMS Test", slug="shisha-bar")
        BusinessSettings.objects.create(business=self.business)
        self.owner = User.objects.create_user(
            username="owner-security",
            email="owner@example.com",
            password="Owner-Test-2026!",
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
        )
        self.customer = User.objects.create_user(
            username="customer-security",
            email="customer@example.com",
            password="Customer-Test-2026!",
        )

    def test_privileged_user_is_forced_to_enroll_mfa(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("mfa_setup"), response.url)

    def test_privileged_api_returns_actionable_mfa_requirement(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("api_me"),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 428)
        self.assertIn(reverse("mfa_setup"), response.json()["action_url"])

    def test_mfa_enrollment_encrypts_secret_and_opens_manager_session(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("mfa_setup"))
        self.assertEqual(response.status_code, 200)

        device = PrivilegedMfaDevice.objects.get(user=self.owner)
        secret = device.get_secret()
        self.assertTrue(secret)
        self.assertNotEqual(device.secret_encrypted, secret)
        self.assertNotIn(secret, device.secret_encrypted)

        code = pyotp.TOTP(secret).now()
        response = self.client.post(
            reverse("mfa_setup"),
            {"code": code, "next": reverse("manager_dashboard")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2FA ist aktiv")

        device.refresh_from_db()
        self.assertTrue(device.is_confirmed)
        self.assertGreaterEqual(device.last_counter, 0)
        self.assertEqual(len(device.recovery_code_hashes), 10)

        response = self.client.get(reverse("manager_dashboard"))
        self.assertNotIn(response.status_code, (401, 403, 428))
        if response.status_code == 302:
            self.assertNotIn(reverse("mfa_setup"), response.url)
            self.assertNotIn(reverse("mfa_challenge"), response.url)

    def test_recovery_codes_are_hashed_and_single_use(self):
        device = PrivilegedMfaDevice.objects.create(user=self.owner)
        device.set_secret(pyotp.random_base32())
        recovery_codes = PrivilegedMfaDevice.generate_recovery_codes()
        device.confirm(recovery_codes)

        plain_code = recovery_codes[0]
        self.assertNotIn(plain_code, device.recovery_code_hashes)
        self.assertTrue(device.consume_recovery_code(plain_code))
        self.assertFalse(device.consume_recovery_code(plain_code))

    def test_non_privileged_user_cannot_enroll_privileged_mfa(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("mfa_setup"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PrivilegedMfaDevice.objects.filter(user=self.customer).exists())

    def test_each_audit_event_receives_an_integrity_seal(self):
        event = AuditEvent.objects.create(
            actor=self.owner,
            business=self.business,
            action="security_test",
            object_type="user",
            object_id=str(self.owner.pk),
            details={"result": "ok"},
        )
        seal = AuditChainSeal.objects.get(audit_event=event)
        self.assertEqual(seal.sequence, 1)
        self.assertEqual(seal.previous_hash, "")
        self.assertEqual(
            seal.event_hash,
            AuditChainSeal.calculate_hash(event, 1, ""),
        )

        output = io.StringIO()
        call_command("verify_audit_chain", stdout=output)
        self.assertIn("Audit-Kette ist gültig", output.getvalue())

    def test_normal_model_save_cannot_modify_audit_event(self):
        event = AuditEvent.objects.create(
            actor=self.owner,
            business=self.business,
            action="original_action",
            object_type="user",
            object_id=str(self.owner.pk),
        )
        event.action = "tampered_action"
        with self.assertRaises(ValidationError):
            event.save()

    def test_bulk_tampering_is_detected_by_chain_verifier(self):
        event = AuditEvent.objects.create(
            actor=self.owner,
            business=self.business,
            action="original_action",
            object_type="user",
            object_id=str(self.owner.pk),
            details={"value": 1},
        )
        AuditEvent.objects.filter(pk=event.pk).update(details={"value": 999})

        with self.assertRaises(CommandError):
            call_command("verify_audit_chain", stdout=io.StringIO(), stderr=io.StringIO())
