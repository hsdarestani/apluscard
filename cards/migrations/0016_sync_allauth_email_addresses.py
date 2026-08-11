from django.db import migrations


def sync_existing_member_emails(apps, schema_editor):
    MemberProfile = apps.get_model("cards", "MemberProfile")
    EmailAddress = apps.get_model("account", "EmailAddress")

    for profile in MemberProfile.objects.select_related("user").iterator():
        email = (profile.user.email or "").strip()
        if not email:
            continue

        address = EmailAddress.objects.filter(
            user_id=profile.user_id,
            email__iexact=email,
        ).first()

        if address is None:
            conflict = EmailAddress.objects.filter(email__iexact=email).exclude(
                user_id=profile.user_id
            ).first()
            if conflict is not None:
                continue

            has_primary = EmailAddress.objects.filter(
                user_id=profile.user_id,
                primary=True,
            ).exists()
            EmailAddress.objects.create(
                user_id=profile.user_id,
                email=email,
                verified=bool(profile.email_verified),
                primary=not has_primary,
            )
            continue

        update_fields = []
        if profile.email_verified and not address.verified:
            address.verified = True
            update_fields.append("verified")

        has_primary = EmailAddress.objects.filter(
            user_id=profile.user_id,
            primary=True,
        ).exists()
        if not has_primary and not address.primary:
            address.primary = True
            update_fields.append("primary")

        if update_fields:
            address.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0001_initial"),
        ("cards", "0015_confirm_existing_member_emails"),
    ]

    operations = [
        migrations.RunPython(sync_existing_member_emails, migrations.RunPython.noop),
    ]
