from django.db import migrations
from django.utils import timezone


def confirm_existing_member_emails(apps, schema_editor):
    MemberProfile = apps.get_model("cards", "MemberProfile")
    now = timezone.now()
    MemberProfile.objects.filter(email_verified=False).update(
        email_verified=True,
        email_verified_at=now,
    )
    MemberProfile.objects.filter(
        email_verified=True,
        email_verified_at__isnull=True,
    ).update(email_verified_at=now)


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0014_backfill_audit_chain"),
    ]

    operations = [
        migrations.RunPython(confirm_existing_member_emails, migrations.RunPython.noop),
    ]
