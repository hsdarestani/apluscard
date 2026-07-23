import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
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
    response = JsonResponse(payload, safe=not isinstance(payload, list), json_dumps_params={"separators": (",", ":")})
    response["Cache-Control"] = f"public, max-age={max_age}"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _build_sams_icon(size):
    image = Image.new("RGBA", (size, size), (8, 5, 14, 255))
    draw = ImageDraw.Draw(image)
    radius = round(size * 0.24)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=(8, 5, 14, 255))

    for index in range(size):
        ratio = index / max(size - 1, 1)
        color = (round(104 + (163 - 104) * ratio), round(37 + (58 - 37) * ratio), 255, 255)
        draw.line((0, index, size, index), fill=color)

    inset = round(size * 0.055)
    draw.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=max(1, radius - inset),
        fill=(10, 6, 17, 245),
    )
    circle_inset = round(size * 0.17)
    draw.ellipse(
        (circle_inset, circle_inset, size - circle_inset, size - circle_inset),
        fill=(119, 42, 255, 255),
        outline=(238, 190, 104, 255),
        width=max(3, round(size * 0.018)),
    )
    draw.arc(
        (circle_inset, circle_inset, size - circle_inset, size - circle_inset),
        205,
        35,
        fill=(255, 218, 145, 255),
        width=max(4, round(size * 0.032)),
    )
    draw.text((size / 2, size / 2), "S", font=_font(round(size * 0.39)), fill=(255, 255, 255, 255), anchor="mm")
    return image


@require_GET
def app_icon(request, size):
    if size not in _ICON_SIZES:
        raise Http404
    output = BytesIO()
    _build_sams_icon(size).save(output, format="PNG", optimize=True)
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
            "description": "Digitale SAMS Mitgliedskarte mit QR-Code, Guthaben, Transaktionen, Standorten und Push-Mitteilungen.",
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
    fingerprints = [fingerprint for fingerprint in settings.ANDROID_APP_SIGNING_SHA256 if _SHA256_FINGERPRINT.fullmatch(fingerprint)]
    payload = []
    if settings.ANDROID_PACKAGE_NAME and fingerprints:
        payload.append(
            {
                "relation": ["delegate_permission/common.handle_all_urls", "delegate_permission/common.get_login_creds"],
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
                "components": [{"/": "/*", "comment": "SAMS Card Universal Links"}],
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
    response["Content-Disposition"] = f'attachment; filename="SAMS-Card-{wallet.member_number}.pkpass"'
    response["Cache-Control"] = "private, no-store"
    return response
