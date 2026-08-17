import uuid

from django.conf import settings
from django.db import models


class EmailVerificationAttempt(models.Model):
    class Trigger(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Registrierung"
        RESEND = "RESEND", "Erneut senden"
        OTHER = "OTHER", "Sonstiges"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Vorbereitet"
        ACCEPTED = "ACCEPTED", "Vom Mail-Backend angenommen"
        FAILED = "FAILED", "Versand fehlgeschlagen"
        CLICKED = "CLICKED", "Link geöffnet"
        CONFIRMED = "CONFIRMED", "E-Mail bestätigt"
        EXPIRED = "EXPIRED", "Link abgelaufen"
        INVALID = "INVALID", "Link ungültig"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_verification_attempts",
    )
    email = models.EmailField(db_index=True)
    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.OTHER)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    token_hash = models.CharField(max_length=64, db_index=True)
    backend = models.CharField(max_length=255, blank=True)
    request_host = models.CharField(max_length=255, blank=True)
    click_count = models.PositiveIntegerField(default=0)
    accepted_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    error_class = models.CharField(max_length=120, blank=True)
    error_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "created_at"], name="cards_email_attempt_idx"),
            models.Index(fields=["status", "created_at"], name="cards_email_status_idx"),
        ]

    def __str__(self):
        return f"{self.email} · {self.get_status_display()} · {self.created_at:%Y-%m-%d %H:%M}"
