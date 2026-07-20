from django.conf import settings
from django.db import migrations


OWNER_PASSWORD_HASH = "pbkdf2_sha256$1000000$LIawDcGNzSZZn1T2wqZaHx$WEFJbwcsQEcZagVv4xGHf2ChXIxkNBFrZmvIvrNUIC0="
STAFF_PASSWORD_HASH = "pbkdf2_sha256$1000000$ExYvdtsMFoFUeZd6pwtn18$MhP5e2EmlWifA+cIEuokgUuiH6sXYq8iIjz5eyUVhEY="


def rotate_demo_passwords(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    User.objects.filter(username="owner").update(password=OWNER_PASSWORD_HASH)
    User.objects.filter(username="staff").update(password=STAFF_PASSWORD_HASH)


class Migration(migrations.Migration):
    dependencies = [("cards", "0002_member_numbers_and_bills")]

    operations = [migrations.RunPython(rotate_demo_passwords, migrations.RunPython.noop)]
