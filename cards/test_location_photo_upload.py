import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pillow_heif import register_heif_opener

from .experience_models import LocationVisual
from .models import Business, Location, Membership


register_heif_opener(thumbnails=False)


class LocationPhotoUploadTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()

        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="photo-owner", password="secret")
        self.business = Business.objects.create(name="Sams Club Lounge", slug="photo-lounge")
        self.location = Location.objects.create(
            business=self.business,
            name="Sams Club Lounge",
            slug="main-lounge",
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
        )
        self.client.force_login(self.owner)

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    def test_owner_can_upload_heic_and_it_is_saved_as_optimized_jpeg(self):
        source = Image.new("RGB", (3200, 1800), (48, 24, 72))
        heic_buffer = BytesIO()
        source.save(heic_buffer, format="HEIF", quality=80)
        upload = SimpleUploadedFile(
            "lounge.heic",
            heic_buffer.getvalue(),
            content_type="image/heic",
        )

        response = self.client.post(
            reverse("location_visual_update"),
            {
                "location": str(self.location.pk),
                "image": upload,
                "short_description": "Lounge und Sportübertragungen",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Foto und Beschreibung")
        visual = LocationVisual.objects.get(location=self.location)
        self.assertTrue(visual.image.name.endswith(".jpg"))
        self.assertEqual(visual.short_description, "Lounge und Sportübertragungen")
        with Image.open(visual.image.path) as saved:
            self.assertEqual(saved.format, "JPEG")
            self.assertLessEqual(max(saved.size), 2400)

    def test_invalid_photo_returns_the_real_validation_error(self):
        upload = SimpleUploadedFile(
            "broken.jpg",
            b"this-is-not-an-image",
            content_type="image/jpeg",
        )

        response = self.client.post(
            reverse("location_visual_update"),
            {
                "location": str(self.location.pk),
                "image": upload,
                "short_description": "Test",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Standortbild konnte nicht gespeichert werden")
        self.assertContains(response, "Foto des Standorts")
        visual = LocationVisual.objects.get(location=self.location)
        self.assertFalse(bool(visual.image))
        self.assertEqual(visual.short_description, "")
