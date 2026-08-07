from django.db import migrations


MAIN_REVIEW_URL = "https://search.google.com/local/writereview?placeid=ChIJsWxV2XAPvUcRapC-3pvplpM"


def set_verified_main_review_url(apps, schema_editor):
    Location = apps.get_model("cards", "Location")
    location = Location.objects.filter(slug="sams-club-lounge").first()
    if location is None or location.google_review_url:
        return
    location.google_review_url = MAIN_REVIEW_URL
    location.save(update_fields=["google_review_url"])


class Migration(migrations.Migration):
    dependencies = [("cards", "0011_test_wallet_marker")]

    operations = [
        migrations.RunPython(set_verified_main_review_url, migrations.RunPython.noop),
    ]
