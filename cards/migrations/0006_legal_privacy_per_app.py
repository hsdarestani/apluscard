import cards.legal_models
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


def create_legal_configurations(apps, schema_editor):
    Business = apps.get_model("cards", "Business")
    Location = apps.get_model("cards", "Location")
    BusinessSettings = apps.get_model("cards", "BusinessSettings")
    LegalConfiguration = apps.get_model("cards", "LegalConfiguration")
    for business in Business.objects.all():
        app_settings = BusinessSettings.objects.filter(business=business).first()
        location = Location.objects.filter(business=business).order_by("position", "name").first()
        LegalConfiguration.objects.get_or_create(
            business=business,
            defaults={
                "app_display_name": business.name,
                "controller_name": (app_settings.legal_name if app_settings else "") or business.name,
                "controller_address": (app_settings.legal_address if app_settings else "") or (location.address if location else ""),
                "vat_id": app_settings.vat_id if app_settings else "",
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cards", "0005_german_interface_choices"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("app_display_name", models.CharField(blank=True, max_length=180)),
                ("controller_name", models.CharField(blank=True, max_length=180)),
                ("controller_address", models.TextField(blank=True)),
                ("representative", models.CharField(blank=True, max_length=180)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("privacy_email", models.EmailField(blank=True, max_length=254)),
                ("contact_phone", models.CharField(blank=True, max_length=80)),
                ("register_court", models.CharField(blank=True, max_length=180)),
                ("register_number", models.CharField(blank=True, max_length=100)),
                ("vat_id", models.CharField(blank=True, max_length=100)),
                ("data_protection_officer", models.TextField(blank=True)),
                ("supervisory_authority", models.CharField(blank=True, max_length=255)),
                ("terms_version", models.CharField(default="1.0", max_length=30)),
                ("privacy_version", models.CharField(default="1.0", max_length=30)),
                ("terms_effective_date", models.DateField(default=django.utils.timezone.localdate)),
                ("privacy_effective_date", models.DateField(default=django.utils.timezone.localdate)),
                ("terms_additional_clauses", models.TextField(blank=True)),
                ("privacy_additional_information", models.TextField(blank=True)),
                ("is_published", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="legal_configuration", to="cards.business")),
            ],
            options={"verbose_name": "Rechtliche App-Konfiguration", "verbose_name_plural": "Rechtliche App-Konfigurationen"},
        ),
        migrations.CreateModel(
            name="PrivacyPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("marketing_push_enabled", models.BooleanField(default=False)),
                ("marketing_email_enabled", models.BooleanField(default=False)),
                ("consented_at", models.DateTimeField(blank=True, null=True)),
                ("withdrawn_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="privacy_preferences", to="cards.business")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="privacy_preferences", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Datenschutz-Einstellung", "verbose_name_plural": "Datenschutz-Einstellungen"},
        ),
        migrations.CreateModel(
            name="LegalAcceptance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(choices=[("TERMS", "AGB"), ("PRIVACY", "Datenschutzhinweise")], max_length=16)),
                ("version", models.CharField(max_length=30)),
                ("source", models.CharField(choices=[("REGISTRATION", "Registrierung"), ("APPLE", "Anmeldung mit Apple"), ("RECONFIRMATION", "Erneute Bestätigung")], max_length=24)),
                ("email_hash", models.CharField(blank=True, max_length=64)),
                ("member_number", models.CharField(blank=True, max_length=8)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("accepted_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="legal_acceptances", to="cards.business")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="legal_acceptances", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Rechtliche Bestätigung", "verbose_name_plural": "Rechtliche Bestätigungen", "ordering": ["-accepted_at"]},
        ),
        migrations.CreateModel(
            name="AccountDeletionRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference_number", models.CharField(default=cards.legal_models.generate_deletion_reference, editable=False, max_length=32, unique=True)),
                ("email", models.EmailField(max_length=254)),
                ("member_number", models.CharField(blank=True, max_length=8)),
                ("reason", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("RECEIVED", "Eingegangen"), ("PROCESSING", "In Bearbeitung"), ("COMPLETED", "Abgeschlossen"), ("REJECTED", "Abgelehnt")], default="RECEIVED", max_length=16)),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("requested_user_agent", models.CharField(blank=True, max_length=500)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("internal_note", models.TextField(blank=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="account_deletion_requests", to="cards.business")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="account_deletion_requests", to=settings.AUTH_USER_MODEL)),
                ("wallet", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="account_deletion_requests", to="cards.wallet")),
            ],
            options={"verbose_name": "Antrag auf Kontolöschung", "verbose_name_plural": "Anträge auf Kontolöschung", "ordering": ["-requested_at"]},
        ),
        migrations.AddConstraint(
            model_name="privacypreference",
            constraint=models.UniqueConstraint(fields=("user", "business"), name="unique_user_business_privacy_preference"),
        ),
        migrations.AddConstraint(
            model_name="legalacceptance",
            constraint=models.UniqueConstraint(fields=("user", "business", "document_type", "version"), name="unique_user_legal_acceptance_version"),
        ),
        migrations.AddIndex(
            model_name="legalacceptance",
            index=models.Index(fields=["business", "document_type", "version"], name="cards_legal_busines_39daf9_idx"),
        ),
        migrations.AddIndex(
            model_name="legalacceptance",
            index=models.Index(fields=["email_hash"], name="cards_legal_email_h_5c2112_idx"),
        ),
        migrations.AddIndex(
            model_name="accountdeletionrequest",
            index=models.Index(fields=["business", "status", "requested_at"], name="cards_accou_busines_5cc41d_idx"),
        ),
        migrations.AddIndex(
            model_name="accountdeletionrequest",
            index=models.Index(fields=["email", "status"], name="cards_accou_email_f_820608_idx"),
        ),
        migrations.RunPython(create_legal_configurations, migrations.RunPython.noop),
    ]
