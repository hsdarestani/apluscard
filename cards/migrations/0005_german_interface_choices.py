from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cards", "0004_sams_final_platform")]

    operations = [
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.CharField(choices=[("OWNER", "Inhaber"), ("MANAGER", "Leitung"), ("STAFF", "Mitarbeiter")], max_length=16),
        ),
        migrations.AlterField(
            model_name="wallet",
            name="status",
            field=models.CharField(choices=[("ACTIVE", "Aktiv"), ("BLOCKED", "Gesperrt"), ("CLOSED", "Geschlossen")], default="ACTIVE", max_length=12),
        ),
        migrations.AlterField(
            model_name="wallet",
            name="tier",
            field=models.CharField(choices=[("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platin")], default="SILVER", max_length=12),
        ),
        migrations.AlterField(
            model_name="ledgerentry",
            name="entry_type",
            field=models.CharField(choices=[("TOPUP", "Aufladung"), ("PURCHASE", "Zahlung"), ("TIP", "Trinkgeld"), ("REFUND", "Erstattung"), ("BONUS", "Bonus"), ("ADJUSTMENT", "Korrektur")], max_length=16),
        ),
        migrations.AlterField(
            model_name="offer",
            name="target_tier",
            field=models.CharField(choices=[("ALL", "Alle"), ("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platin")], default="ALL", max_length=12),
        ),
        migrations.AlterField(
            model_name="pushdevice",
            name="platform",
            field=models.CharField(choices=[("IOS", "iOS"), ("ANDROID", "Android"), ("WEB", "Browser")], max_length=12),
        ),
    ]
