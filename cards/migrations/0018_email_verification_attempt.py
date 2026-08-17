import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0017_sync_verified_allauth_back_to_members"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailVerificationAttempt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("trigger", models.CharField(choices=[("REGISTRATION", "Registrierung"), ("RESEND", "Erneut senden"), ("OTHER", "Sonstiges")], default="OTHER", max_length=16)),
                ("status", models.CharField(choices=[("PENDING", "Vorbereitet"), ("ACCEPTED", "Vom Mail-Backend angenommen"), ("FAILED", "Versand fehlgeschlagen"), ("CLICKED", "Link geöffnet"), ("CONFIRMED", "E-Mail bestätigt"), ("EXPIRED", "Link abgelaufen"), ("INVALID", "Link ungültig")], db_index=True, default="PENDING", max_length=16)),
                ("token_hash", models.CharField(db_index=True, max_length=64)),
                ("backend", models.CharField(blank=True, max_length=255)),
                ("request_host", models.CharField(blank=True, max_length=255)),
                ("click_count", models.PositiveIntegerField(default=0)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("clicked_at", models.DateTimeField(blank=True, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("error_class", models.CharField(blank=True, max_length=120)),
                ("error_detail", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="email_verification_attempts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="emailverificationattempt",
            index=models.Index(fields=["email", "created_at"], name="cards_email_attempt_idx"),
        ),
        migrations.AddIndex(
            model_name="emailverificationattempt",
            index=models.Index(fields=["status", "created_at"], name="cards_email_status_idx"),
        ),
    ]
