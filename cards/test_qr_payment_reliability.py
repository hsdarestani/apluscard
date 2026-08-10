from django.core import signing
from django.test import TestCase

from .compliance_qr import (
    QR_PREFIX,
    QR_SHORT_SIGNING_SALT,
    QR_SIGNING_SALT,
    issue_wallet_qr,
    resolve_payment_qr,
    wallet_qr_payload,
)
from .tests import PlatformMixin


class PaymentQrReliabilityTests(PlatformMixin, TestCase):
    def setUp(self):
        self.create_platform()

    def _legacy_token(self):
        payload = {
            "v": 1,
            "wallet_id": str(self.wallet.pk),
            "card_id": str(self.wallet.qr_token),
        }
        return f"{QR_PREFIX}{signing.dumps(payload, salt=QR_SIGNING_SALT, compress=True)}"

    def _previous_compact_token(self):
        signed = signing.TimestampSigner(salt=QR_SHORT_SIGNING_SALT).sign(str(self.wallet.qr_token))
        return f"{QR_PREFIX}{signed}"

    def test_previous_rotating_token_remains_compact_and_resolves(self):
        token = issue_wallet_qr(self.wallet)
        legacy = self._legacy_token()

        self.assertTrue(token.startswith(QR_PREFIX))
        self.assertLess(len(token), len(legacy))
        self.assertLess(len(token), 64)
        self.assertNotEqual(token, str(self.wallet.qr_token))
        self.assertEqual(resolve_payment_qr(token, business=self.business), self.wallet)

    def test_customer_display_qr_exactly_matches_apple_wallet_code(self):
        payload = wallet_qr_payload(self.wallet)

        self.assertEqual(payload["token"], str(self.wallet.qr_token))
        self.assertTrue(payload["data_uri"].startswith("data:image/svg+xml;base64,"))
        self.assertTrue(payload["static"])
        self.assertIsNone(payload["expires_in"])
        self.assertEqual(payload["refresh_in"], 0)
        self.assertEqual(resolve_payment_qr(payload["token"], business=self.business), self.wallet)

    def test_previous_compact_rotating_token_remains_compatible(self):
        self.assertEqual(
            resolve_payment_qr(self._previous_compact_token(), business=self.business),
            self.wallet,
        )

    def test_legacy_rotating_token_remains_compatible(self):
        self.assertEqual(
            resolve_payment_qr(self._legacy_token(), business=self.business),
            self.wallet,
        )

    def test_cashier_can_use_visible_member_number_as_manual_fallback(self):
        self.assertEqual(
            resolve_payment_qr(self.wallet.member_number, business=self.business),
            self.wallet,
        )

    def test_member_number_requires_business_scope(self):
        with self.assertRaises(signing.BadSignature):
            resolve_payment_qr(self.wallet.member_number)

    def test_expired_previous_rotating_token_cannot_fall_back_to_embedded_card_id(self):
        token = issue_wallet_qr(self.wallet)
        with self.assertRaises(signing.BadSignature):
            resolve_payment_qr(token, business=self.business, max_age=-1)

    def test_plain_apple_wallet_uuid_still_resolves(self):
        self.assertEqual(
            resolve_payment_qr(str(self.wallet.qr_token), business=self.business),
            self.wallet,
        )
