# Generated manually for SAMS native push delivery tracking.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0009_payment_flow_tip_euros"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Ausstehend"),
                            ("PROCESSING", "Wird gesendet"),
                            ("SENT", "Gesendet"),
                            ("SKIPPED", "Übersprungen"),
                            ("RETRY", "Erneut versuchen"),
                            ("FAILED", "Fehlgeschlagen"),
                        ],
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_error", models.TextField(blank=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "notification",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_delivery",
                        to="cards.appnotification",
                    ),
                ),
            ],
            options={
                "ordering": ["next_attempt_at", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="pushdelivery",
            index=models.Index(fields=["status", "next_attempt_at"], name="cards_push_status_next_idx"),
        ),
    ]
