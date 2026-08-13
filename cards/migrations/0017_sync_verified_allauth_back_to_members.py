from django.db import migrations
from django.utils import timezone


def sync_verified_allauth_back_to_members(apps, schema_editor):
    MemberProfile = apps.get_model("cards", "MemberProfile")
    EmailAddress = apps.get_model("account", "EmailAddress")

    now = timezone.now()
    verified_user_ids = EmailAddress.objects.filter(verified=True).values_list(
        "user_id", flat=True
    )

    MemberProfile.objects.filter(
        user_id__in=verified_user_ids,
        email_verified=False,
    ).update(
        email_verified=True,
        email_verified_at=now,
    )

    MemberProfile.objects.filter(
        user_id__in=verified_user_ids,
        email_verified=True,
        email_verified_at__isnull=True,
    ).update(email_verified_at=now)


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0001_initial"),
        ("cards", "0016_sync_allauth_email_addresses"),
    ]

    operations = [
        migrations.RunPython(
            sync_verified_allauth_back_to_members,
            migrations.RunPython.noop,
        ),
    ]
