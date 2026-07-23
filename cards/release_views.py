import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET


_SHA256_FINGERPRINT = re.compile(r"^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$")


def _json_response(payload, *, max_age=300):
    response = JsonResponse(
        payload,
        safe=not isinstance(payload, list),
        json_dumps_params={"separators": (",", ":")},
    )
    response["Cache-Control"] = f"public, max-age={max_age}"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def manifest(request):
    return _json_response(
        {
            "id": "/",
            "name": settings.APP_NAME,
            "short_name": settings.APP_SHORT_NAME,
            "description": "Digitale A+ Mitgliedskarte mit QR-Code, Guthaben, Transaktionen, Standorten und Mitteilungen.",
            "lang": "de-DE",
            "dir": "ltr",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
            "orientation": "portrait-primary",
            "background_color": "#05030b",
            "theme_color": "#09050f",
            "categories": ["lifestyle", "utilities"],
            "prefer_related_applications": False,
            "icons": [
                {
                    "src": "/static/cards/icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
            "shortcuts": [
                {
                    "name": "Mitgliedskarte",
                    "short_name": "Karte",
                    "url": "/customer/",
                    "icons": [{"src": "/static/cards/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
                },
                {
                    "name": "Mitteilungen",
                    "short_name": "Mitteilungen",
                    "url": "/mitteilungen/",
                    "icons": [{"src": "/static/cards/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
                },
            ],
        }
    )


@require_GET
def android_asset_links(request):
    fingerprints = [
        fingerprint
        for fingerprint in settings.ANDROID_APP_SIGNING_SHA256
        if _SHA256_FINGERPRINT.fullmatch(fingerprint)
    ]
    payload = []
    if settings.ANDROID_PACKAGE_NAME and fingerprints:
        payload.append(
            {
                "relation": [
                    "delegate_permission/common.handle_all_urls",
                    "delegate_permission/common.get_login_creds",
                ],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.ANDROID_PACKAGE_NAME,
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        )
    return _json_response(payload)


@require_GET
def apple_app_site_association(request):
    details = []
    if settings.IOS_APP_TEAM_ID and settings.IOS_BUNDLE_ID:
        details.append(
            {
                "appIDs": [f"{settings.IOS_APP_TEAM_ID}.{settings.IOS_BUNDLE_ID}"],
                "components": [
                    {"/": "/*", "comment": "A+ Card Universal Links"},
                ],
            }
        )
    return _json_response(
        {
            "applinks": {"details": details},
            "webcredentials": {
                "apps": [f"{settings.IOS_APP_TEAM_ID}.{settings.IOS_BUNDLE_ID}"]
                if settings.IOS_APP_TEAM_ID and settings.IOS_BUNDLE_ID
                else []
            },
        }
    )
