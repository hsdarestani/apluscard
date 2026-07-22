from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def migrate_payment_flow(apps, schema_editor):
    BusinessSettings = apps.get_model("cards", "BusinessSettings")
    PaymentRequest = apps.get_model("cards", "PaymentRequest")

    for settings_obj in BusinessSettings.objects.all():
        old_options = [
            settings_obj.tip_option_1,
            settings_obj.tip_option_2,
            settings_obj.tip_option_3,
            settings_obj.tip_option_4,
        ]
        settings_obj.require_customer_confirmation = False
        settings_obj.offer_scheduling_enabled = True
        update_fields = ["require_customer_confirmation", "offer_scheduling_enabled"]
        if old_options == [Decimal("0.00"), Decimal("5.00"), Decimal("10.00"), Decimal("15.00")]:
            settings_obj.tip_option_1 = Decimal("0.00")
            settings_obj.tip_option_2 = Decimal("2.00")
            settings_obj.tip_option_3 = Decimal("5.00")
            settings_obj.tip_option_4 = Decimal("10.00")
            update_fields.extend(["tip_option_1", "tip_option_2", "tip_option_3", "tip_option_4"])
        settings_obj.save(update_fields=update_fields)

    PaymentRequest.objects.filter(status="PENDING").update(status="CANCELLED")
    PaymentRequest.objects.update(tip_selected_amount=F("tip_amount"))


def reverse_payment_flow(apps, schema_editor):
    BusinessSettings = apps.get_model("cards", "BusinessSettings")
    BusinessSettings.objects.update(require_customer_confirmation=True)


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0008_member_experience"),
    ]

    operations = [
        migrations.RenameField(
            model_name="paymentrequest",
            old_name="tip_percentage",
            new_name="tip_selected_amount",
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="require_customer_confirmation",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="tip_option_1",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8),
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="tip_option_2",
            field=models.DecimalField(decimal_places=2, default=Decimal("2.00"), max_digits=8),
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="tip_option_3",
            field=models.DecimalField(decimal_places=2, default=Decimal("5.00"), max_digits=8),
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="tip_option_4",
            field=models.DecimalField(decimal_places=2, default=Decimal("10.00"), max_digits=8),
        ),
        migrations.AlterField(
            model_name="businesssettings",
            name="offer_scheduling_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="paymentrequest",
            name="customer_confirmation_required",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="paymentrequest",
            name="tip_selected_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AlterField(
            model_name="transactioncase",
            name="opened_by_role",
            field=models.CharField(
                choices=[
                    ("CUSTOMER", "Kunde"),
                    ("STAFF", "Mitarbeiter"),
                    ("MANAGEMENT", "Verwaltung"),
                ],
                max_length=12,
            ),
        ),
        migrations.RunPython(migrate_payment_flow, reverse_payment_flow),
    ]
