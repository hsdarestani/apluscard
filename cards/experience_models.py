import secrets
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .models import Business, LedgerEntry, Location, Wallet


def generate_case_number():
    return f"F-{timezone.now():%Y%m%d}-{secrets.token_hex(4).upper()}"


class MemberNumberSequence(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    next_number = models.PositiveBigIntegerField(default=101)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Nummernkreis für Mitgliedsnummern"
        verbose_name_plural = "Nummernkreise für Mitgliedsnummern"

    def __str__(self):
        return f"Nächste Mitgliedsnummer: {self.next_number}"


class LocationVisual(models.Model):
    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="visual")
    image = models.ImageField(upload_to="locations/%Y/%m/", blank=True)
    short_description = models.CharField(max_length=180, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Standortbild"
        verbose_name_plural = "Standortbilder"

    def __str__(self):
        return f"Bild · {self.location.name}"


class TransactionCase(models.Model):
    class OpenedByRole(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Kunde"
        STAFF = "STAFF", "Mitarbeiter"

    class Reason(models.TextChoices):
        WRONG_AMOUNT = "WRONG_AMOUNT", "Falscher Betrag"
        WRONG_MEMBER = "WRONG_MEMBER", "Falsches Mitglied belastet"
        DUPLICATE = "DUPLICATE", "Doppelte Buchung"
        NOT_RECOGNIZED = "NOT_RECOGNIZED", "Transaktion nicht erkannt"
        TIP_ERROR = "TIP_ERROR", "Trinkgeld falsch"
        OTHER = "OTHER", "Anderer Grund"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Eingegangen"
        IN_REVIEW = "IN_REVIEW", "In Prüfung"
        APPROVED = "APPROVED", "Genehmigt und erstattet"
        REJECTED = "REJECTED", "Abgelehnt"
        CANCELLED = "CANCELLED", "Zurückgezogen"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_number = models.CharField(max_length=32, unique=True, default=generate_case_number, editable=False, db_index=True)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="transaction_cases")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="transaction_cases")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="transaction_cases")
    ledger_entry = models.ForeignKey(LedgerEntry, on_delete=models.PROTECT, related_name="transaction_cases")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="opened_transaction_cases")
    opened_by_role = models.CharField(max_length=12, choices=OpenedByRole.choices)
    reason = models.CharField(max_length=24, choices=Reason.choices)
    description = models.TextField()
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    manager_note = models.TextField(blank=True)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_transaction_cases")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    refund_entry = models.OneToOneField(LedgerEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="refund_case")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transaktionsfall"
        verbose_name_plural = "Transaktionsfälle"
        indexes = [
            models.Index(fields=["business", "status", "created_at"], name="cards_case_biz_status_idx"),
            models.Index(fields=["wallet", "created_at"], name="cards_case_wallet_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ledger_entry", "opened_by"],
                condition=Q(status__in=["OPEN", "IN_REVIEW"]),
                name="unique_open_case_per_entry_user",
            )
        ]

    @property
    def refundable_amount(self):
        return abs(self.ledger_entry.amount) if self.ledger_entry.amount < 0 else None

    @property
    def can_be_reviewed(self):
        return self.status in {self.Status.OPEN, self.Status.IN_REVIEW}

    def __str__(self):
        return f"{self.case_number} · {self.get_status_display()}"
