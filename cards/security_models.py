import base64
import hashlib
import json
import secrets
import string

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from .models import AuditEvent, Business


def _mfa_cipher():
    """Return a stable Fernet cipher derived from the dedicated key or SECRET_KEY.

    Production should set MFA_ENCRYPTION_KEY to an independent, backed-up secret.
    Falling back to SECRET_KEY keeps upgrades safe for existing installations.
    """

    source = getattr(settings, "MFA_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class PrivilegedMfaDevice(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="privileged_mfa_device",
    )
    secret_encrypted = models.TextField(blank=True)
    is_confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_counter = models.BigIntegerField(default=-1)
    recovery_code_hashes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zwei-Faktor-Gerät"
        verbose_name_plural = "Zwei-Faktor-Geräte"

    def set_secret(self, secret):
        self.secret_encrypted = _mfa_cipher().encrypt(secret.encode("ascii")).decode("ascii")

    def get_secret(self):
        if not self.secret_encrypted:
            return ""
        try:
            return _mfa_cipher().decrypt(self.secret_encrypted.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError, UnicodeDecodeError):
            return ""

    @staticmethod
    def generate_recovery_codes(count=10):
        alphabet = string.ascii_uppercase + string.digits
        return [
            f"{''.join(secrets.choice(alphabet) for _ in range(4))}-{''.join(secrets.choice(alphabet) for _ in range(4))}"
            for _ in range(count)
        ]

    def replace_recovery_codes(self, codes):
        self.recovery_code_hashes = [make_password(code.upper()) for code in codes]

    def consume_recovery_code(self, candidate):
        normalized = (candidate or "").strip().upper()
        for index, encoded in enumerate(list(self.recovery_code_hashes or [])):
            if check_password(normalized, encoded):
                remaining = list(self.recovery_code_hashes)
                remaining.pop(index)
                self.recovery_code_hashes = remaining
                self.save(update_fields=["recovery_code_hashes", "updated_at"])
                return True
        return False

    def confirm(self, recovery_codes):
        self.is_confirmed = True
        self.confirmed_at = timezone.now()
        self.replace_recovery_codes(recovery_codes)
        self.save(
            update_fields=[
                "is_confirmed",
                "confirmed_at",
                "recovery_code_hashes",
                "updated_at",
            ]
        )

    def __str__(self):
        status = "aktiv" if self.is_confirmed else "Einrichtung offen"
        return f"2FA · {self.user} · {status}"


class AuditChainSeal(models.Model):
    """Hash-chain seal for detecting later alteration of audit records."""

    audit_event = models.OneToOneField(
        AuditEvent,
        on_delete=models.PROTECT,
        related_name="integrity_seal",
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="audit_chain_seals",
    )
    sequence = models.PositiveBigIntegerField()
    previous_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["business_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "sequence"],
                name="unique_audit_chain_sequence",
            )
        ]
        verbose_name = "Audit-Integritätssiegel"
        verbose_name_plural = "Audit-Integritätssiegel"

    @staticmethod
    def canonical_payload(event, sequence, previous_hash):
        return json.dumps(
            {
                "sequence": sequence,
                "previous_hash": previous_hash,
                "event_id": event.pk,
                "business_id": event.business_id,
                "actor_id": event.actor_id,
                "action": event.action,
                "object_type": event.object_type,
                "object_id": event.object_id,
                "details": event.details,
                "ip_address": str(event.ip_address or ""),
                "created_at": event.created_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

    @classmethod
    def calculate_hash(cls, event, sequence, previous_hash):
        return hashlib.sha256(
            cls.canonical_payload(event, sequence, previous_hash)
        ).hexdigest()

    def __str__(self):
        return f"{self.business} · #{self.sequence} · {self.event_hash[:12]}"
