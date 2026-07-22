from django.db import migrations


LOCATIONS = (
    {
        "name": "Sams Club Lounge",
        "slug": "sams-club-lounge",
        "address": "Frankfurter Straße 198\n61118 Bad Vilbel\nTelefon: 06101/5969952",
        "position": 1,
    },
    {
        "name": "Sams Club Lounge CITY",
        "slug": "sams-club-lounge-city",
        "address": "Frankfurter Straße 38\n61118 Bad Vilbel\nTelefon: 06101/5969440",
        "position": 2,
    },
    {
        "name": "DIMA Sportsbar",
        "slug": "dima-sportsbar",
        "address": "Frankfurter Straße 36\n61118 Bad Vilbel\nTelefon: 06101/5969440",
        "position": 3,
    },
)


def set_real_locations(apps, schema_editor):
    Business = apps.get_model("cards", "Business")
    Location = apps.get_model("cards", "Location")

    business = Business.objects.filter(slug="shisha-bar").first()
    if business is None:
        return

    existing_locations = list(
        Location.objects.filter(business=business).order_by("position", "created_at")
    )
    retained_ids = []

    for index, location_data in enumerate(LOCATIONS):
        location = Location.objects.filter(
            business=business,
            slug=location_data["slug"],
        ).first()
        if location is None and index < len(existing_locations):
            location = existing_locations[index]
        if location is None:
            location = Location(business=business)

        for field, value in location_data.items():
            setattr(location, field, value)
        location.is_active = True
        location.save()
        retained_ids.append(location.pk)

    Location.objects.filter(business=business).exclude(pk__in=retained_ids).update(is_active=False)


def reverse_locations(apps, schema_editor):
    Location = apps.get_model("cards", "Location")
    Business = apps.get_model("cards", "Business")
    business = Business.objects.filter(slug="shisha-bar").first()
    if business is None:
        return
    for position in range(1, 4):
        location = Location.objects.filter(business=business, position=position).first()
        if location:
            location.name = f"SAMS Club Lounge {position}"
            location.slug = f"sams-{position}"
            location.address = ""
            location.is_active = True
            location.save(update_fields=["name", "slug", "address", "is_active"])


class Migration(migrations.Migration):
    dependencies = [("cards", "0006_legal_privacy_per_app")]

    operations = [migrations.RunPython(set_real_locations, reverse_locations)]
