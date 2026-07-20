import secrets
import uuid

import cards.models
from django.db import migrations, models


def populate_numbers(apps, schema_editor):
    Wallet = apps.get_model("cards", "Wallet")
    LedgerEntry = apps.get_model("cards", "LedgerEntry")

    used_member_numbers = set(
        Wallet.objects.exclude(member_number__isnull=True).values_list("member_number", flat=True)
    )
    for wallet in Wallet.objects.filter(member_number__isnull=True).iterator():
        while True:
            number = str(secrets.randbelow(90_000_000) + 10_000_000)
            if number not in used_member_numbers:
                used_member_numbers.add(number)
                wallet.member_number = number
                wallet.save(update_fields=["member_number"])
                break

    used_bill_numbers = set(
        LedgerEntry.objects.exclude(bill_number__isnull=True).values_list("bill_number", flat=True)
    )
    for entry in LedgerEntry.objects.filter(bill_number__isnull=True).iterator():
        date_part = entry.created_at.strftime("%Y%m%d") if entry.created_at else "00000000"
        while True:
            number = f"B-{date_part}-{uuid.uuid4().hex[:10].upper()}"
            if number not in used_bill_numbers:
                used_bill_numbers.add(number)
                entry.bill_number = number
                entry.save(update_fields=["bill_number"])
                break


class Migration(migrations.Migration):
    dependencies = [("cards", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="wallet",
            name="member_number",
            field=models.CharField(blank=True, db_index=True, max_length=8, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="ledgerentry",
            name="bill_number",
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True, unique=True),
        ),
        migrations.RunPython(populate_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="wallet",
            name="member_number",
            field=models.CharField(db_index=True, default=cards.models.generate_member_number, editable=False, max_length=8, unique=True),
        ),
        migrations.AlterField(
            model_name="ledgerentry",
            name="bill_number",
            field=models.CharField(db_index=True, default=cards.models.generate_bill_number, editable=False, max_length=32, unique=True),
        ),
    ]
