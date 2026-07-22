from django.test import TestCase
from django.urls import reverse


class PublicLocationTests(TestCase):
    def test_landing_page_contains_all_real_locations(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        for expected in (
            "Sams Club Lounge",
            "Frankfurter Straße 198",
            "06101 / 5969952",
            "Sams Club Lounge CITY",
            "Frankfurter Straße 38",
            "DIMA Sportsbar",
            "Frankfurter Straße 36",
            "06101 / 5969440",
        ):
            with self.subTest(expected=expected):
                self.assertContains(response, expected)
