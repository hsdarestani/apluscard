from django.db import models
from django.utils import timezone


class PushDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Ausstehend"
        PROCESSING = "PROCESSING", "Wird gesendet"
        SENT = "SENT", "Gesendet"
        SKIPPED = "SKIPPED", "Übersprungen"
        RETRY = "RETRY", "Erneut versuchen"
        FAILED = "FAILED", "Fehlgeschlagen"

    notification = models.OneToOneField(
        "cards.AppNotification",
        on_delete=models.CASCADE,
        related_name="push_delivery",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_attempt_at", "created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="cards_push_status_next_idx"),
        ]

    def __str__(self):
        return f"Push {self.notification_id} · {self.status}"
