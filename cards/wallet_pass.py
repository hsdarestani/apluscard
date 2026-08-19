import base64
import hashlib
import json
import math
import zipfile
from io import BytesIO

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .branding import load_brand_icon


DARK = (1, 1, 5, 255)
MIDNIGHT = (4, 3, 10, 255)
PURPLE = (154, 58, 255, 255)
PURPLE_CORE = (236, 165, 255, 255)
PURPLE_HOT = (205, 110, 255, 255)
PURPLE_GLOW = (118, 28, 255, 255)
VIOLET = (196, 104, 255, 255)
WHITE = (255, 255, 255, 255)
SOFT_WHITE = (245, 243, 250, 255)


def _decode_secret(value):
    value = (value or "").strip()
    if not value:
        return b""
    if "-----BEGIN" in value:
        return value.replace("\\n", "\n").encode("utf-8")
    return base64.b64decode("".join(value.split()))


def _load_certificate(value):
    raw = _decode_secret(value)
    if not raw:
        raise ImproperlyConfigured("Apple-Wallet-Zertifikat fehlt.")
    try:
        return x509.load_pem_x509_certificate(raw)
    except ValueError:
        return x509.load_der_x509_certificate(raw)


def _load_signing_identity():
    p12_raw = _decode_secret(settings.APPLE_WALLET_P12_BASE64)
    if not p12_raw:
        raise ImproperlyConfigured("Apple-Wallet-P12 fehlt.")
    password = settings.APPLE_WALLET_P12_PASSWORD.encode("utf-8") if settings.APPLE_WALLET_P12_PASSWORD else None
    private_key, certificate, chain = pkcs12.load_key_and_certificates(p12_raw, password)
    if private_key is None or certificate is None:
        raise ImproperlyConfigured("Apple-Wallet-P12 enthält kein gültiges Zertifikat mit privatem Schlüssel.")
    return private_key, certificate, list(chain or [])


def _font(size, *, bold=True):
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _vertical_gradient(width, height, top, bottom):
    image = Image.new("RGBA", (width, height), top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(round(top[index] + (bottom[index] - top[index]) * ratio) for index in range(4))
        draw.line((0, y, width, y), fill=color)
    return image


def _icon_image(size):
    exact_icon = load_brand_icon(size)
    if exact_icon is not None:
        return exact_icon

    image = _vertical_gradient(size, size, (13, 8, 22, 255), DARK)
    draw = ImageDraw.Draw(image)
    radius = max(4, round(size * 0.22))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    image.putalpha(mask)

    inset = round(size * 0.11)
    draw.ellipse((inset, inset, size - inset, size - inset), fill=(126, 48, 255, 255))
    draw.arc(
        (inset, inset, size - inset, size - inset),
        start=205,
        end=35,
        fill=VIOLET,
        width=max(2, round(size * 0.045)),
    )
    draw.text((size / 2, size / 2), "SCL", font=_font(max(9, round(size * 0.29))), fill=WHITE, anchor="mm")
    return image


def _logo_image(width, height):
    """Reference-like neon SCL wordmark, used once in the Wallet header."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    big_font = _font(max(24, round(height * 0.58)), bold=False)
    small_font = _font(max(7, round(height * 0.15)), bold=False)

    # Wide violet halo behind the wordmark.
    outer_glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    outer_draw = ImageDraw.Draw(outer_glow)
    outer_draw.text((2, -3), "SCL", font=big_font, fill=(158, 38, 255, 190))
    outer_draw.text((4, round(height * 0.64)), "SAMS CLUB LOUNGE", font=small_font, fill=(140, 40, 255, 145))
    outer_glow = outer_glow.filter(ImageFilter.GaussianBlur(max(4, height // 10)))
    image = Image.alpha_composite(image, outer_glow)

    # Tighter glow gives the reference its crisp neon edge.
    inner_glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    inner_draw = ImageDraw.Draw(inner_glow)
    inner_draw.text((2, -3), "SCL", font=big_font, fill=(205, 92, 255, 215))
    inner_draw.text((4, round(height * 0.64)), "SAMS CLUB LOUNGE", font=small_font, fill=(169, 72, 255, 175))
    inner_glow = inner_glow.filter(ImageFilter.GaussianBlur(max(2, height // 20)))
    image = Image.alpha_composite(image, inner_glow)

    draw = ImageDraw.Draw(image)
    draw.text((2, -3), "SCL", font=big_font, fill=(235, 171, 255, 255))
    draw.text((4, round(height * 0.64)), "SAMS CLUB LOUNGE", font=small_font, fill=(188, 103, 255, 255))
    return image


def _strip_image(width, height):
    """Reference-style Neon Lounge: near-black with a thin asymmetric neon arc."""
    image = _vertical_gradient(width, height, MIDNIGHT, DARK)

    points = []
    for x in range(-12, width + 13, 2):
        ratio = x / max(width, 1)
        r = max(0.0, min(1.0, ratio))
        # Matches the reference: gentle entry on the left, a shallow dip,
        # then a stronger climb and brighter finish on the right.
        y = height * (0.58 + 0.15 * math.sin(r * math.pi) - 0.13 * r)
        points.append((x, round(y)))

    # Very restrained ambient haze under the arc; the card itself stays black.
    ambient = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ambient_draw = ImageDraw.Draw(ambient)
    ambient_draw.ellipse(
        (-round(width * 0.10), round(height * 0.48), round(width * 0.35), round(height * 1.12)),
        fill=(85, 18, 210, 20),
    )
    ambient_draw.ellipse(
        (round(width * 0.55), round(height * 0.34), round(width * 1.12), round(height * 1.08)),
        fill=(125, 34, 255, 34),
    )
    ambient = ambient.filter(ImageFilter.GaussianBlur(max(16, height // 5)))
    image = Image.alpha_composite(image, ambient)

    # Bright right-side hotspot, visible in the reference.
    hot_r = 0.87
    hot_y = height * (0.58 + 0.15 * math.sin(hot_r * math.pi) - 0.13 * hot_r)
    hotspot = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hotspot_draw = ImageDraw.Draw(hotspot)
    hotspot_draw.ellipse(
        (
            round(width * 0.70),
            round(hot_y - height * 0.30),
            round(width * 1.08),
            round(hot_y + height * 0.30),
        ),
        fill=(147, 46, 255, 82),
    )
    hotspot = hotspot.filter(ImageFilter.GaussianBlur(max(18, height // 4)))
    image = Image.alpha_composite(image, hotspot)

    # Draw variable-strength glows so the arc is subtler on the left and hotter on the right.
    outer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    outer_draw = ImageDraw.Draw(outer)
    inner = Image.new("RGBA", image.size, (0, 0, 0, 0))
    inner_draw = ImageDraw.Draw(inner)
    hot = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hot_draw = ImageDraw.Draw(hot)

    segment_count = max(len(points) - 1, 1)
    for index in range(segment_count):
        p = index / segment_count
        p_hot = p ** 1.7
        p0 = points[index]
        p1 = points[index + 1]
        outer_alpha = round(72 + 105 * p_hot)
        inner_alpha = round(118 + 100 * p_hot)
        hot_alpha = round(135 + 95 * p_hot)
        outer_draw.line((p0, p1), fill=(96, 22, 255, outer_alpha), width=max(12, height // 9))
        inner_draw.line((p0, p1), fill=(162, 58, 255, inner_alpha), width=max(6, height // 18))
        hot_draw.line((p0, p1), fill=(211, 108, 255, hot_alpha), width=max(3, height // 30))

    outer = outer.filter(ImageFilter.GaussianBlur(max(13, height // 7)))
    image = Image.alpha_composite(image, outer)
    inner = inner.filter(ImageFilter.GaussianBlur(max(7, height // 15)))
    image = Image.alpha_composite(image, inner)
    hot = hot.filter(ImageFilter.GaussianBlur(max(3, height // 28)))
    image = Image.alpha_composite(image, hot)

    # Core neon and a soft highlight/shadow pair for dimensionality.
    draw = ImageDraw.Draw(image)
    for index in range(segment_count):
        p = index / segment_count
        p_hot = p ** 1.55
        p0 = points[index]
        p1 = points[index + 1]
        core = (
            round(222 + 14 * p_hot),
            round(143 + 22 * p_hot),
            255,
            255,
        )
        draw.line((p0, p1), fill=core, width=max(2, height // 64))

    highlight = [(x, y - 1) for x, y in points]
    draw.line(highlight, fill=(255, 224, 255, 105), width=1)

    reflection = [(x, y + max(5, height // 24)) for x, y in points]
    draw.line(reflection, fill=(96, 24, 170, 34), width=1)

    # A faint blurred shadow immediately below the arc keeps the glow soft rather than flat.
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.line(reflection, fill=(70, 12, 120, 70), width=max(5, height // 22))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(8, height // 14)))
    image = Image.alpha_composite(image, shadow)
    return image


def _png_bytes(image):
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _pass_files(wallet, request):
    terms_url = request.build_absolute_uri(reverse("app_terms", args=[wallet.business.slug]))
    privacy_url = request.build_absolute_uri(reverse("app_privacy_policy", args=[wallet.business.slug]))
    delete_url = request.build_absolute_uri(reverse("app_account_deletion", args=[wallet.business.slug]))
    barcode = {
        "format": "PKBarcodeFormatQR",
        "message": str(wallet.qr_token),
        "messageEncoding": "iso-8859-1",
    }
    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": settings.APPLE_WALLET_PASS_TYPE_ID,
        "serialNumber": str(wallet.pk),
        "teamIdentifier": settings.APPLE_WALLET_TEAM_ID,
        "organizationName": settings.APP_PUBLISHER,
        "description": "Digitale Sams Club Lounge Mitgliedskarte",
        "foregroundColor": "rgb(245, 243, 250)",
        "backgroundColor": "rgb(1, 1, 5)",
        "labelColor": "rgb(186, 116, 255)",
        "sharingProhibited": True,
        "suppressStripShine": True,
        "barcodes": [barcode],
        "barcode": barcode,
        "storeCard": {
            "headerFields": [
                {"key": "memberNumber", "label": "MITGLIEDSNR.", "value": wallet.member_number},
            ],
            "secondaryFields": [
                {"key": "memberName", "label": "MITGLIED", "value": wallet.display_name},
            ],
            "auxiliaryFields": [
                {"key": "tier", "label": "STATUS", "value": wallet.get_tier_display()},
                {"key": "validAt", "label": "GÜLTIG", "value": "Alle Standorte"},
            ],
            "backFields": [
                {"key": "partner", "label": "SAMS Standorte", "value": "Sams Club Lounge · Sams Club Lounge CITY · DIMA Sportsbar"},
                {"key": "balanceInfo", "label": "Aktuelles Guthaben", "value": f"{wallet.balance:.2f} €"},
                {"key": "provider", "label": "Bereitgestellt von", "value": settings.APP_PUBLISHER},
                {"key": "usage", "label": "Verwendung", "value": "Diese digitale Mitgliedskarte ist persönlich und nicht übertragbar."},
                {"key": "support", "label": "Support", "value": settings.APP_SUPPORT_EMAIL},
                {"key": "terms", "label": "AGB", "value": terms_url},
                {"key": "privacy", "label": "Datenschutz", "value": privacy_url},
                {"key": "deletion", "label": "Konto und Daten löschen", "value": delete_url},
            ],
        },
    }
    return {
        "pass.json": json.dumps(pass_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "icon.png": _png_bytes(_icon_image(29)),
        "icon@2x.png": _png_bytes(_icon_image(58)),
        "icon@3x.png": _png_bytes(_icon_image(87)),
        "logo.png": _png_bytes(_logo_image(190, 54)),
        "logo@2x.png": _png_bytes(_logo_image(380, 108)),
        "strip.png": _png_bytes(_strip_image(375, 123)),
        "strip@2x.png": _png_bytes(_strip_image(750, 246)),
    }


def build_pkpass(wallet, request):
    if not settings.APPLE_WALLET_ENABLED:
        raise ImproperlyConfigured("Apple Wallet ist noch nicht mit einem Pass-Type-Zertifikat verbunden.")

    files = _pass_files(wallet, request)
    manifest = {filename: hashlib.sha1(content).hexdigest() for filename, content in files.items()}
    manifest_bytes = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8")

    private_key, certificate, chain = _load_signing_identity()
    wwdr = _load_certificate(settings.APPLE_WALLET_WWDR_CERT_BASE64)
    builder = pkcs7.PKCS7SignatureBuilder().set_data(manifest_bytes).add_signer(certificate, private_key, hashes.SHA256())
    builder = builder.add_certificate(wwdr)
    for certificate_in_chain in chain:
        builder = builder.add_certificate(certificate_in_chain)
    signature = builder.sign(
        serialization.Encoding.DER,
        [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
    )

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("signature", signature)
    return output.getvalue()
