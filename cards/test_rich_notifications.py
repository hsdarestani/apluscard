from io import BytesIO
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings

from .operations_views import _notification_data, _store_notification_image
from .push_services import _notification_image_url, _string_data


class RichNotificationImageTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.media_dir = TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            MEDIA_URL="/media/",
            APP_PUBLIC_BASE_URL="https://app.samsclublounge.de",
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.media_dir.cleanup()

    @staticmethod
    def _image_upload(*, image_format="PNG"):
        buffer = BytesIO()
        Image.new("RGB", (80, 40), "white").save(buffer, format=image_format)
        extension = "jpg" if image_format == "JPEG" else image_format.lower()
        content_type = "image/jpeg" if image_format == "JPEG" else f"image/{image_format.lower()}"
        return SimpleUploadedFile(f"notification.{extension}", buffer.getvalue(), content_type=content_type)

    def test_optional_image_is_validated_stored_and_added_to_notification_data(self):
        request = self.factory.post(
            "/manager/notifications/broadcast/",
            data={"target_url": "/customer/#offers", "image": self._image_upload()},
        )
        image_url = _store_notification_image(request)
        data = _notification_data(request, image_url=image_url)

        self.assertTrue(image_url.startswith("/media/notification-images/"))
        self.assertEqual(data["image_url"], image_url)
        self.assertEqual(data["url"], "/customer/#offers")

    def test_invalid_image_is_rejected(self):
        request = self.factory.post(
            "/manager/notifications/broadcast/",
            data={"image": SimpleUploadedFile("fake.jpg", b"not-an-image", content_type="image/jpeg")},
        )
        with self.assertRaisesMessage(Exception, "Das Bild konnte nicht gelesen werden"):
            _store_notification_image(request)

    def test_push_data_uses_public_absolute_image_url(self):
        notification = SimpleNamespace(
            pk="123",
            kind="OFFER",
            data={"url": "/mitteilungen/", "image_url": "/media/notification-images/example.jpg"},
        )
        self.assertEqual(
            _notification_image_url(notification),
            "https://app.samsclublounge.de/media/notification-images/example.jpg",
        )
        payload = _string_data(notification)
        self.assertEqual(payload["url"], "https://app.samsclublounge.de/mitteilungen/")
        self.assertEqual(
            payload["image_url"],
            "https://app.samsclublounge.de/media/notification-images/example.jpg",
        )
