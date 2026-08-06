import json
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class NativeCameraPermissionAssetsTests(SimpleTestCase):
    def test_mobile_shell_includes_native_camera_plugin(self):
        package = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
        self.assertIn("@capacitor/camera", package["dependencies"])

    def test_staff_and_manager_scanners_request_permission_first(self):
        permission_bridge = ROOT / "cards" / "static" / "cards" / "camera-permissions.js"
        self.assertTrue(permission_bridge.is_file())
        bridge_source = permission_bridge.read_text(encoding="utf-8")
        self.assertIn("requestPermissions", bridge_source)
        self.assertIn("permissions: ['camera']", bridge_source)

        for template_name in ("staff_dashboard.html", "manager_dashboard.html"):
            template = ROOT / "cards" / "templates" / "cards" / template_name
            source = template.read_text(encoding="utf-8")
            self.assertIn("cards/camera-permissions.js", source)
            self.assertIn("prepareForScanner", source)
