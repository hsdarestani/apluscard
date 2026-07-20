import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def generate_member_number():
    """Generate a customer-facing eight digit member number."""
    return str(secrets.randbelow(90_000_000) + 10_000_000)


def generate_bill_number():
    """Generate a readable, globally unique digital receipt number."""
    return f"B-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"


class Business(models.Model):
    name = models.CharField(max_length=140)
    slug = models.SlugField(unique=True)
    currency = models.CharField(max_length=3, default="EUR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        STAFF = "STAFF", "Staff"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="business_memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "business"], name="unique_business_membership")]
        ordering = ["business__name", "user__username"]

    def __str__(self):
        return f"{self.user} · {self.business} · {self.role}"


class Wallet(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        BLOCKED = "BLOCKED", "Blocked"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="wallets")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="wallets")
    member_number = models.CharField(max_length=8, unique=True, default=generate_member_number, editable=False, db_index=True)
    display_name = models.CharField(max_length=140)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["business", "owner"], condition=Q(owner__isnull=False), name="unique_user_wallet_per_business")]
        ordering = ["display_name"]

    def __str__(self):
        return f"{self.display_name} · {self.business}"


class LedgerEntry(models.Model):
    class Type(models.TextChoices):
        TOPUP = "TOPUP", "Top-up"
        PURCHASE = "PURCHASE", "Purchase"
        REFUND = "REFUND", "Refund"
        BONUS = "BONUS", "Bonus"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill_number = models.CharField(max_length=32, unique=True, default=generate_bill_number, editable=False, db_index=True)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="ledger_entries")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="ledger_entries")
    entry_type = models.CharField(max_length=16, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    order_reference = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="performed_ledger_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(amount=0), name="ledger_amount_not_zero"),
            models.UniqueConstraint(fields=["business", "idempotency_key"], condition=~Q(idempotency_key=""), name="unique_business_idempotency_key"),
        ]
        indexes = [models.Index(fields=["business", "created_at"]), models.Index(fields=["wallet", "created_at"]), models.Index(fields=["order_reference"])]

    def __str__(self):
        return f"{self.entry_type} {self.amount} · {self.wallet}"


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events")
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="audit_events")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "created_at"])]

    def __str__(self):
        return f"{self.action} · {self.object_type}:{self.object_id}"
