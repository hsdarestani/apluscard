from django.conf import settings
from django.db import models

from .models import Wallet


class TestWalletMarker(models.Model):
    """Explicitly marks a wallet whose records may be purged in a test environment.

    Production keeps ALLOW_TEST_DATA_PURGE disabled, so this marker alone never
    authorizes deletion. Both the environment flag and this database marker are
    required.
    """

    wallet = models.OneToOneField(
        Wallet,
        on_delete=models.PROTECT,
        related_name="test_data_marker",
    )
    reason = models.CharField(max_length=255)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_test_wallets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Testkonto-Markierung"
        verbose_name_plural = "Testkonto-Markierungen"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Testkonto {self.wallet.member_number} · {self.reason}"
