import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def bootstrap_sams_platform(apps, schema_editor):
    Business = apps.get_model("cards", "Business")
    BusinessSettings = apps.get_model("cards", "BusinessSettings")
    Location = apps.get_model("cards", "Location")
    MemberProfile = apps.get_model("cards", "MemberProfile")
    Wallet = apps.get_model("cards", "Wallet")

    for business in Business.objects.all():
        BusinessSettings.objects.get_or_create(business=business)
        if not Location.objects.filter(business=business).exists():
            for position in range(1, 4):
                Location.objects.create(id=uuid.uuid4(), business=business, name=f"SAMS Club Lounge {position}", slug=f"sams-{position}", position=position, is_active=True)

    for wallet in Wallet.objects.exclude(owner_id__isnull=True).iterator():
        MemberProfile.objects.get_or_create(user_id=wallet.owner_id, defaults={"email_verified": True, "age_confirmed": True})


class Migration(migrations.Migration):
    dependencies = [("cards", "0003_rotate_demo_account_passwords")]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=140)),
                ("slug", models.SlugField(max_length=80)),
                ("address", models.TextField(blank=True)),
                ("google_review_url", models.URLField(blank=True)),
                ("instagram_url", models.URLField(blank=True)),
                ("tiktok_url", models.URLField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="locations", to="cards.business")),
            ],
            options={"ordering": ["position", "name"]},
        ),
        migrations.CreateModel(
            name="BusinessSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("require_customer_confirmation", models.BooleanField(default=True)),
                ("tip_option_1", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("tip_option_2", models.DecimalField(decimal_places=2, default=Decimal("5.00"), max_digits=5)),
                ("tip_option_3", models.DecimalField(decimal_places=2, default=Decimal("10.00"), max_digits=5)),
                ("tip_option_4", models.DecimalField(decimal_places=2, default=Decimal("15.00"), max_digits=5)),
                ("tip_allocation", models.CharField(choices=[("TEAM", "Team"), ("EMPLOYEE", "Einzelne Person")], default="TEAM", max_length=12)),
                ("gold_threshold", models.DecimalField(decimal_places=2, default=Decimal("500.00"), max_digits=12)),
                ("platinum_threshold", models.DecimalField(decimal_places=2, default=Decimal("700.00"), max_digits=12)),
                ("birthday_bonus", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("official_invoice_enabled", models.BooleanField(default=False)),
                ("legal_name", models.CharField(blank=True, max_length=180)),
                ("legal_address", models.TextField(blank=True)),
                ("tax_number", models.CharField(blank=True, max_length=80)),
                ("vat_id", models.CharField(blank=True, max_length=80)),
                ("daily_summary_enabled", models.BooleanField(default=False)),
                ("weekly_summary_enabled", models.BooleanField(default=False)),
                ("offer_scheduling_enabled", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="app_settings", to="cards.business")),
            ],
        ),
        migrations.CreateModel(
            name="MemberProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("birth_date", models.DateField(blank=True, null=True)),
                ("age_confirmed", models.BooleanField(default=False)),
                ("email_verified", models.BooleanField(default=False)),
                ("email_verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="member_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(model_name="membership", name="can_manage_content", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="wallet", name="monthly_topup_total", field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
        migrations.AddField(model_name="wallet", name="tier", field=models.CharField(choices=[("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platinum")], default="SILVER", max_length=12)),
        migrations.CreateModel(
            name="PaymentRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("base_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("tip_percentage", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("tip_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("tip_recipient", models.CharField(choices=[("TEAM", "Team"), ("EMPLOYEE", "Einzelne Person")], default="TEAM", max_length=12)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("order_reference", models.CharField(blank=True, max_length=100)),
                ("customer_confirmation_required", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("PENDING", "Wartet auf Bestätigung"), ("CONFIRMED", "Bestätigt"), ("CANCELLED", "Storniert"), ("EXPIRED", "Abgelaufen")], default="PENDING", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="cards.business")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_payment_requests", to=settings.AUTH_USER_MODEL)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="cards.location")),
                ("purchase_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_payment_request", to="cards.ledgerentry")),
                ("tip_employee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="received_tip_requests", to=settings.AUTH_USER_MODEL)),
                ("tip_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tip_payment_request", to="cards.ledgerentry")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="cards.wallet")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["wallet", "status", "created_at"], name="cards_pay_wallet_status_idx"), models.Index(fields=["business", "location", "created_at"], name="cards_pay_biz_loc_created_idx")]},
        ),
        migrations.AddField(model_name="ledgerentry", name="location", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="cards.location")),
        migrations.AddField(model_name="ledgerentry", name="payment_request", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ledger_entries", to="cards.paymentrequest")),
        migrations.AlterField(model_name="ledgerentry", name="entry_type", field=models.CharField(choices=[("TOPUP", "Top-up"), ("PURCHASE", "Purchase"), ("TIP", "Trinkgeld"), ("REFUND", "Refund"), ("BONUS", "Bonus"), ("ADJUSTMENT", "Adjustment")], max_length=16)),
        migrations.AddIndex(model_name="ledgerentry", index=models.Index(fields=["location", "created_at"], name="cards_ledger_loc_created_idx")),
        migrations.CreateModel(
            name="Offer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=180)),
                ("body", models.TextField()),
                ("image", models.ImageField(blank=True, upload_to="offers/%Y/%m/")),
                ("target_tier", models.CharField(choices=[("ALL", "Alle"), ("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platinum")], default="ALL", max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="cards.business")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_offers", to=settings.AUTH_USER_MODEL)),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="cards.location")),
            ], options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(name="ReviewStatus", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("completed_at", models.DateTimeField(blank=True, null=True)), ("location", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_statuses", to="cards.location")), ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_statuses", to="cards.wallet"))]),
        migrations.CreateModel(name="AppNotification", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("kind", models.CharField(choices=[("PAYMENT", "Zahlung"), ("OFFER", "Angebot"), ("BIRTHDAY", "Geburtstag"), ("SYSTEM", "System")], default="SYSTEM", max_length=16)), ("title", models.CharField(max_length=160)), ("body", models.TextField()), ("data", models.JSONField(blank=True, default=dict)), ("is_read", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="cards.business")), ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="cards.location")), ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="app_notifications", to=settings.AUTH_USER_MODEL))], options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["recipient", "is_read", "created_at"], name="cards_notif_rec_read_idx")]}),
        migrations.CreateModel(name="PushDevice", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("platform", models.CharField(choices=[("IOS", "iOS"), ("ANDROID", "Android"), ("WEB", "Web")], max_length=12)), ("token", models.CharField(max_length=512, unique=True)), ("is_active", models.BooleanField(default=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_devices", to=settings.AUTH_USER_MODEL))]),
        migrations.AddConstraint(model_name="location", constraint=models.UniqueConstraint(fields=("business", "slug"), name="unique_business_location_slug")),
        migrations.AddConstraint(model_name="reviewstatus", constraint=models.UniqueConstraint(fields=("wallet", "location"), name="unique_wallet_location_review")),
        migrations.RunPython(bootstrap_sams_platform, migrations.RunPython.noop),
    ]
