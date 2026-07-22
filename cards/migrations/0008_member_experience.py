import django.db.models.deletion
import uuid

import cards.experience_models
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


def migrate_member_numbers(apps, schema_editor):
    Wallet = apps.get_model("cards", "Wallet")
    MemberNumberSequence = apps.get_model("cards", "MemberNumberSequence")
    Location = apps.get_model("cards", "Location")
    LocationVisual = apps.get_model("cards", "LocationVisual")

    wallets = list(Wallet.objects.all().order_by("created_at", "pk"))
    for index, wallet in enumerate(wallets, start=1):
        Wallet.objects.filter(pk=wallet.pk).update(member_number=f"X{index:07d}")
    for number, wallet in enumerate(wallets, start=101):
        Wallet.objects.filter(pk=wallet.pk).update(member_number=str(number))

    MemberNumberSequence.objects.update_or_create(
        pk=1,
        defaults={"next_number": 101 + len(wallets)},
    )
    for location in Location.objects.all():
        LocationVisual.objects.get_or_create(location=location)


def reverse_member_numbers(apps, schema_editor):
    Wallet = apps.get_model("cards", "Wallet")
    for index, wallet in enumerate(Wallet.objects.all().order_by("created_at", "pk"), start=1):
        Wallet.objects.filter(pk=wallet.pk).update(member_number=f"{10_000_000 + index}")


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0007_real_sams_locations"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberNumberSequence",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("next_number", models.PositiveBigIntegerField(default=101)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Nummernkreis für Mitgliedsnummern",
                "verbose_name_plural": "Nummernkreise für Mitgliedsnummern",
            },
        ),
        migrations.CreateModel(
            name="LocationVisual",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(blank=True, upload_to="locations/%Y/%m/")),
                ("short_description", models.CharField(blank=True, max_length=180)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("location", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="visual", to="cards.location")),
            ],
            options={
                "verbose_name": "Standortbild",
                "verbose_name_plural": "Standortbilder",
            },
        ),
        migrations.CreateModel(
            name="TransactionCase",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("case_number", models.CharField(db_index=True, default=cards.experience_models.generate_case_number, editable=False, max_length=32, unique=True)),
                ("opened_by_role", models.CharField(choices=[("CUSTOMER", "Kunde"), ("STAFF", "Mitarbeiter")], max_length=12)),
                ("reason", models.CharField(choices=[("WRONG_AMOUNT", "Falscher Betrag"), ("WRONG_MEMBER", "Falsches Mitglied belastet"), ("DUPLICATE", "Doppelte Buchung"), ("NOT_RECOGNIZED", "Transaktion nicht erkannt"), ("TIP_ERROR", "Trinkgeld falsch"), ("OTHER", "Anderer Grund")], max_length=24)),
                ("description", models.TextField()),
                ("requested_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("status", models.CharField(choices=[("OPEN", "Eingegangen"), ("IN_REVIEW", "In Prüfung"), ("APPROVED", "Genehmigt und erstattet"), ("REJECTED", "Abgelehnt"), ("CANCELLED", "Zurückgezogen")], default="OPEN", max_length=16)),
                ("manager_note", models.TextField(blank=True)),
                ("approved_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transaction_cases", to="cards.business")),
                ("ledger_entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transaction_cases", to="cards.ledgerentry")),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transaction_cases", to="cards.location")),
                ("opened_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="opened_transaction_cases", to=settings.AUTH_USER_MODEL)),
                ("refund_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="refund_case", to="cards.ledgerentry")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_transaction_cases", to=settings.AUTH_USER_MODEL)),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transaction_cases", to="cards.wallet")),
            ],
            options={
                "verbose_name": "Transaktionsfall",
                "verbose_name_plural": "Transaktionsfälle",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["business", "status", "created_at"], name="cards_case_biz_status_idx"),
                    models.Index(fields=["wallet", "created_at"], name="cards_case_wallet_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="transactioncase",
            constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["OPEN", "IN_REVIEW"])), fields=("ledger_entry", "opened_by"), name="unique_open_case_per_entry_user"),
        ),
        migrations.RunPython(migrate_member_numbers, reverse_member_numbers),
    ]
