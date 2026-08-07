from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cards import experience_services
from cards.legal_models import PrivacyPreference
from cards.models import AppNotification, Business, Location, Membership, Wallet
from cards.push_models import PushDelivery


class ReviewLinkManagementTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS", slug="review-test")
        self.owner = get_user_model().objects.create_user(
            username="review-owner@example.com",
            email="review-owner@example.com",
            password="test-password-123",
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
            is_active=True,
        )
        self.location = Location.objects.create(
            business=self.business,
            name="SAMS Test",
            slug="sams-test",
        )
        self.client.force_login(self.owner)

    def test_owner_can_update_review_and_social_links_for_existing_location(self):
        review_url = "https://search.google.com/local/writereview?placeid=verified-test-id"
        response = self.client.post(
            reverse("location_links_update", args=[self.location.pk]),
            {
                "google_review_url": review_url,
                "instagram_url": "https://www.instagram.com/sams.test/",
                "tiktok_url": "https://www.tiktok.com/@sams.test",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.location.refresh_from_db()
        self.assertEqual(self.location.google_review_url, review_url)
        self.assertEqual(self.location.instagram_url, "https://www.instagram.com/sams.test/")
        self.assertEqual(self.location.tiktok_url, "https://www.tiktok.com/@sams.test")

    def test_location_links_reject_plain_http(self):
        response = self.client.post(
            reverse("location_links_update", args=[self.location.pk]),
            {"google_review_url": "http://example.com/review"},
        )

        self.assertEqual(response.status_code, 302)
        self.location.refresh_from_db()
        self.assertEqual(self.location.google_review_url, "")


class NativeDataExportTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS", slug="export-test")
        self.user = get_user_model().objects.create_user(
            username="export@example.com",
            email="export@example.com",
            first_name="Export",
            last_name="Member",
            password="test-password-123",
        )
        self.wallet = Wallet.objects.create(
            business=self.business,
            owner=self.user,
            display_name="Export Member",
            email=self.user.email,
        )
        self.client.force_login(self.user)

    def test_native_handoff_returns_short_lived_external_download_url(self):
        response = self.client.get(reverse("customer_data_export"), {"handoff": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["expires_in"], 120)
        download_path = urlsplit(payload["url"]).path
        self.assertIn("/datenschutz/datenexport/download/", download_path)

        # The external browser does not share the Capacitor WebView session.
        self.client.logout()
        download = self.client.get(download_path)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment;", download["Content-Disposition"])
        self.assertIn('"email": "export@example.com"', download.content.decode("utf-8"))

    def test_regular_browser_export_still_downloads_directly(self):
        response = self.client.get(reverse("customer_data_export"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(self.wallet.member_number, response["Content-Disposition"])


class MarketingPushConsentTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="SAMS", slug="push-consent-test")
        User = get_user_model()
        self.opted_in = User.objects.create_user(
            username="push-in@example.com",
            email="push-in@example.com",
        )
        self.opted_out = User.objects.create_user(
            username="push-out@example.com",
            email="push-out@example.com",
        )
        PrivacyPreference.objects.create(
            user=self.opted_in,
            business=self.business,
            marketing_push_enabled=True,
        )
        PrivacyPreference.objects.create(
            user=self.opted_out,
            business=self.business,
            marketing_push_enabled=False,
        )

    def test_offer_is_in_app_for_both_but_push_only_for_consented_member(self):
        with self.captureOnCommitCallbacks(execute=True):
            notifications = experience_services.create_notifications(
                users=[self.opted_in, self.opted_out],
                business=self.business,
                kind=AppNotification.Kind.OFFER,
                title="Angebot",
                body="Testangebot",
            )

        self.assertEqual(len(notifications), 2)
        self.assertEqual(AppNotification.objects.filter(kind=AppNotification.Kind.OFFER).count(), 2)
        deliveries = PushDelivery.objects.filter(notification__in=notifications)
        self.assertEqual(deliveries.count(), 1)
        self.assertEqual(deliveries.get().notification.recipient_id, self.opted_in.pk)

    def test_transactional_payment_push_does_not_require_marketing_consent(self):
        with self.captureOnCommitCallbacks(execute=True):
            notifications = experience_services.create_notifications(
                users=[self.opted_out],
                business=self.business,
                kind=AppNotification.Kind.PAYMENT,
                title="Zahlung",
                body="Transaktionshinweis",
            )

        self.assertEqual(len(notifications), 1)
        self.assertTrue(PushDelivery.objects.filter(notification=notifications[0]).exists())
