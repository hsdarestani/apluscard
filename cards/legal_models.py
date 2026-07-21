import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import Business, Wallet


def generate_deletion_reference():
    return f"L-{timezone.now():%Y%m%d}-{secrets.token_hex(4).upper()}"


class LegalConfiguration(models.Model):
    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="legal_configuration",
    )
    app_display_name = models.CharField(max_length=180, blank=True)
    controller_name = models.CharField(max_length=180, blank=True)
    controller_address = models.TextField(blank=True)
    representative = models.CharField(max_length=180, blank=True)
    contact_email = models.EmailField(blank=True)
    privacy_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=80, blank=True)
    register_court = models.CharField(max_length=180, blank=True)
    register_number = models.CharField(max_length=100, blank=True)
    vat_id = models.CharField(max_length=100, blank=True)
    data_protection_officer = models.TextField(blank=True)
    supervisory_authority = models.CharField(max_length=255, blank=True)
    terms_version = models.CharField(max_length=30, default="1.0")
    privacy_version = models.CharField(max_length=30, default="1.0")
    terms_effective_date = models.DateField(default=timezone.localdate)
    privacy_effective_date = models.DateField(default=timezone.localdate)
    terms_additional_clauses = models.TextField(blank=True)
    privacy_additional_information = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rechtliche App-Konfiguration"
        verbose_name_plural = "Rechtliche App-Konfigurationen"

    @property
    def display_name(self):
        return self.app_display_name or self.business.name

    @property
    def responsible_name(self):
        return self.controller_name or self.business.name

    def __str__(self):
        return f"Rechtliches · {self.business}"


class LegalAcceptance(models.Model):
    class DocumentType(models.TextChoices):
        TERMS = "TERMS", "AGB"
        PRIVACY = "PRIVACY", "Datenschutzhinweise"

    class Source(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Registrierung"
        APPLE = "APPLE", "Anmeldung mit Apple"
        RECONFIRMATION = "RECONFIRMATION", "Erneute Bestätigung"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legal_acceptances",
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="legal_acceptances",
    )
    document_type = models.CharField(max_length=16, choices=DocumentType.choices)
    version = models.CharField(max_length=30)
    source = models.CharField(max_length=24, choices=Source.choices)
    email_hash = models.CharField(max_length=64, blank=True)
    member_number = models.CharField(max_length=8, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rechtliche Bestätigung"
        verbose_name_plural = "Rechtliche Bestätigungen"
        ordering = ["-accepted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "business", "document_type", "version"],
                name="unique_user_legal_acceptance_version",
            )
        ]
        indexes = [
            models.Index(fields=["business", "document_type", "version"]),
            models.Index(fields=["email_hash"]),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} {self.version} · {self.business}"


class PrivacyPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="privacy_preferences",
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="privacy_preferences",
    )
    marketing_push_enabled = models.BooleanField(default=False)
    marketing_email_enabled = models.BooleanField(default=False)
    consented_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Datenschutz-Einstellung"
        verbose_name_plural = "Datenschutz-Einstellungen"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "business"],
                name="unique_user_business_privacy_preference",
            )
        ]

    def __str__(self):
        return f"Datenschutz · {self.user} · {self.business}"


class AccountDeletionRequest(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Eingegangen"
        PROCESSING = "PROCESSING", "In Bearbeitung"
        COMPLETED = "COMPLETED", "Abgeschlossen"
        REJECTED = "REJECTED", "Abgelehnt"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(
        max_length=32,
        unique=True,
        default=generate_deletion_reference,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_deletion_requests",
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="account_deletion_requests",
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_deletion_requests",
    )
    email = models.EmailField()
    member_number = models.CharField(max_length=8, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    requested_ip = models.GenericIPAddressField(null=True, blank=True)
    requested_user_agent = models.CharField(max_length=500, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    internal_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Antrag auf Kontolöschung"
        verbose_name_plural = "Anträge auf Kontolöschung"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["business", "status", "requested_at"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        return f"{self.reference_number} · {self.business} · {self.get_status_display()}"
