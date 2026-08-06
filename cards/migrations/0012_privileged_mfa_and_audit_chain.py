from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cards", "0011_test_wallet_marker"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrivilegedMfaDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("secret_encrypted", models.TextField(blank=True)),
                ("is_confirmed", models.BooleanField(default=False)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("last_counter", models.BigIntegerField(default=-1)),
                ("recovery_code_hashes", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="privileged_mfa_device",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Zwei-Faktor-Gerät",
                "verbose_name_plural": "Zwei-Faktor-Geräte",
            },
        ),
        migrations.CreateModel(
            name="AuditChainSeal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveBigIntegerField()),
                ("previous_hash", models.CharField(blank=True, max_length=64)),
                ("event_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "audit_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="integrity_seal",
                        to="cards.auditevent",
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_chain_seals",
                        to="cards.business",
                    ),
                ),
            ],
            options={
                "verbose_name": "Audit-Integritätssiegel",
                "verbose_name_plural": "Audit-Integritätssiegel",
                "ordering": ["business_id", "sequence"],
            },
        ),
        migrations.AddConstraint(
            model_name="auditchainseal",
            constraint=models.UniqueConstraint(
                fields=("business", "sequence"),
                name="unique_audit_chain_sequence",
            ),
        ),
    ]
