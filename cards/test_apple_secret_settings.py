import base64
import os
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings import _apple_private_key


PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
TEST-APPLE-PRIVATE-KEY
-----END PRIVATE KEY-----"""


class AppleSecretSettingsTests(SimpleTestCase):
    def test_raw_pem_is_accepted_from_base64_named_secret(self):
        with patch.dict(
            os.environ,
            {"APPLE_PRIVATE_KEY": "", "APPLE_PRIVATE_KEY_BASE64": PRIVATE_KEY},
            clear=False,
        ):
            self.assertEqual(_apple_private_key(), PRIVATE_KEY)

    def test_actual_base64_is_decoded(self):
        encoded = base64.b64encode(PRIVATE_KEY.encode("utf-8")).decode("ascii")
        with patch.dict(
            os.environ,
            {"APPLE_PRIVATE_KEY": "", "APPLE_PRIVATE_KEY_BASE64": encoded},
            clear=False,
        ):
            self.assertEqual(_apple_private_key(), PRIVATE_KEY)

    def test_invalid_base64_is_rejected(self):
        with patch.dict(
            os.environ,
            {"APPLE_PRIVATE_KEY": "", "APPLE_PRIVATE_KEY_BASE64": "not-a-private-key"},
            clear=False,
        ):
            self.assertEqual(_apple_private_key(), "")
