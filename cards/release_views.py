import re
from io import BytesIO

from PIL import Image, ImageDraw
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET

from .models import Wallet
from .wallet_pass import build_pkpass


_SHA256_FINGERPRINT = re.compile(r"^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$")
_ICON_SIZES = {192, 512}


def _json_response(payload, *, max_age=300):
    response = JsonResponse(
        payload,
        safe=not isinstance(payload, list),
        json_dumps_params={"separators": (",", ":")},
    )
    response["Cache-Control"] = f"public, max-age={max_age}"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _scale_points(points, size):
    factor = size / 512
    return [(round(x * factor), round(y * factor)) for x, y in points]


def _build_aplus_icon(size):
    image = Image.new("RGBA", (size, size), (7, 4, 11, 255))
    draw = ImageDraw.Draw(image)
    radius = round(size * 0.242)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=(7, 4, 11, 255))

    for index in range(size):
        ratio = index / max(size - 1, 1)
        color = (
            round(122 + (237 - 122) * ratio),
            round(53 + (46 - 53) * ratio),
            round(255 + (166 - 255) * ratio),
            255,
        )
        draw.line((index, 0, index, size), fill=color)
    inset = round(size * 0.028)
    draw.rounded_rectangle((inset, inset, size - inset, size - inset), radius=radius, fill=(9, 5, 15, 245))

    ring_box = _scale_points([(68, 68), (444, 444)], size)
    ring_width = max(5, round(size * 0.027))
    draw.ellipse((*ring_box[0], *ring_box[1]), outline=(190, 63, 230, 255), width=ring_width)
    inner_box = _scale_points([(99, 99), (413, 413)], size)
    draw.ellipse((*inner_box[0], *inner_box[1]), fill=(11, 7, 17, 255), outline=(255, 255, 255, 22), width=max(1, round(size * 0.006)))

    a_shape = _scale_points([(119, 366), (220, 142), (291, 142), (393, 366), (325, 366), (304, 316), (202, 316), (182, 366)], size)
    draw.polygon(a_shape, fill=(255, 255, 255, 255))
    a_cutout = _scale_points([(223, 265), (284, 265), (254, 190)], size)
    draw.polygon(a_cutout, fill=(11, 7, 17, 255))

    plus = _scale_points([(337, 118), (376, 118), (376, 166), (424, 166), (424, 205), (376, 205), (376, 253), (337, 253), (337, 205), (289, 205), (289, 166), (337, 166)], size)
    draw.polygon(plus, fill=(237, 46, 166, 255))
    return image


@require_GET
def app_icon(request, size):
    if size not in _ICON_SIZES:
        raise Http404
    output = BytesIO()
    _build_aplus_icon(size).save(output, format="PNG", optimize=True)
    response = HttpResponse(output.getvalue(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
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
                {"src": "/app-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/app-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
            "shortcuts": [
                {
                    "name": "Mitgliedskarte",
                    "short_name": "Karte",
                    "url": "/customer/",
                    "icons": [{"src": "/app-icon-192.png", "sizes": "192x192", "type": "image/png"}],
                },
                {
                    "name": "Mitteilungen",
                    "short_name": "Mitteilungen",
                    "url": "/mitteilungen/",
                    "icons": [{"src": "/app-icon-192.png", "sizes": "192x192", "type": "image/png"}],
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


@login_required
@require_GET
def apple_wallet_pass(request):
    wallet = get_object_or_404(Wallet.objects.select_related("business"), owner=request.user)
    try:
        pass_data = build_pkpass(wallet, request)
    except ImproperlyConfigured as exc:
        messages.error(request, str(exc))
        return redirect("customer_dashboard")
    response = HttpResponse(pass_data, content_type="application/vnd.apple.pkpass")
    response["Content-Disposition"] = f'attachment; filename="Aplus-Card-{wallet.member_number}.pkpass"'
    response["Cache-Control"] = "private, no-store"
    return response
