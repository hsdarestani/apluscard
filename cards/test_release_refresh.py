from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from .release_refresh import get_release_version
from .security_middleware import SecurityHeadersMiddleware


class DeploymentRefreshTests(SimpleTestCase):
    def test_deployment_version_endpoint_is_never_cached(self):
        response = self.client.get(reverse("deployment_version"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], get_release_version())
        self.assertEqual(len(payload["version"]), 16)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertEqual(response["Expires"], "0")

    def test_html_responses_are_never_cached(self):
        middleware = SecurityHeadersMiddleware(
            lambda request: HttpResponse("ok", content_type="text/html; charset=utf-8")
        )
        response = middleware(RequestFactory().get("/accounts/login/"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("must-revalidate", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertEqual(response["Expires"], "0")

    def test_runtime_checks_release_on_resume_and_forces_reload(self):
        runtime = (
            Path(settings.BASE_DIR) / "cards" / "static" / "cards" / "runtime-fixes.js"
        ).read_text(encoding="utf-8")
        self.assertIn("/release/version/", runtime)
        self.assertIn("visibilitychange", runtime)
        self.assertIn("pageshow", runtime)
        self.assertIn("cache: 'no-store'", runtime)
        self.assertIn("window.location.replace", runtime)
