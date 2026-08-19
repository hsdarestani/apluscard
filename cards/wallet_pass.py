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


DARK = (4, 3, 8, 255)
MIDNIGHT = (11, 7, 19, 255)
PURPLE = (111, 36, 220, 255)
VIOLET = (164, 74, 255, 255)
PINK = (226, 59, 174, 255)
GOLD = (205, 156, 75, 255)
GOLD_LIGHT = (246, 211, 143, 255)
WHITE = (255, 255, 255, 255)


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
    draw.ellipse((inset, inset, size - inset, size - inset), fill=PURPLE)
    draw.arc(
        (inset, inset, size - inset, size - inset),
        start=205,
        end=35,
        fill=GOLD_LIGHT,
        width=max(2, round(size * 0.045)),
    )
    draw.text((size / 2, size / 2), "SCL", font=_font(max(9, round(size * 0.29))), fill=WHITE, anchor="mm")
    return image


def _logo_image(width, height):
    """Render exactly one brand mark in the Wallet header, without duplicate logo text."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    icon_size = min(height, 46 if height >= 46 else height)
    emblem = _icon_image(icon_size)
    image.alpha_composite(emblem, (0, round((height - icon_size) / 2)))
    return image


def _strip_image(width, height):
    """Luxury SAMS artwork: dark glass, violet light and restrained champagne-gold curves."""
    image = _vertical_gradient(width, height, MIDNIGHT, DARK)

    # Broad ambient light. The artwork deliberately contains no logo or text so
    # the single brand mark in the Wallet header remains the only logo on-card.
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (-round(width * 0.34), round(height * 0.03), round(width * 0.64), round(height * 1.70)),
        fill=(118, 36, 235, 118),
    )
    glow_draw.ellipse(
        (round(width * 0.25), -round(height * 1.05), round(width * 0.96), round(height * 0.96)),
        fill=(177, 61, 255, 54),
    )
    glow_draw.ellipse(
        (round(width * 0.72), -round(height * 0.40), round(width * 1.20), round(height * 0.72)),
        fill=(235, 73, 177, 24),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(max(16, height // 5)))
    image = Image.alpha_composite(image, glow)

    # A soft violet light ribbon gives the card a premium focal point without
    # competing with member data below the strip.
    ribbon_glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ribbon_draw = ImageDraw.Draw(ribbon_glow)
    points = []
    for x in range(-12, width + 13, 2):
        ratio = x / max(width, 1)
        y = (
            height * 0.62
            + math.sin(ratio * math.pi * 1.28 - 0.62) * height * 0.18
            - ratio * height * 0.18
        )
        points.append((x, round(y)))
    ribbon_draw.line(points, fill=(147, 58, 255, 180), width=max(8, height // 11))
    ribbon_glow = ribbon_glow.filter(ImageFilter.GaussianBlur(max(8, height // 12)))
    image = Image.alpha_composite(image, ribbon_glow)

    draw = ImageDraw.Draw(image)

    # Crisp violet and champagne-gold signatures on the light ribbon.
    draw.line(points, fill=(160, 80, 255, 178), width=max(2, height // 61))
    gold_points = [(x, y - max(4, height // 28)) for x, y in points]
    draw.line(gold_points, fill=(229, 184, 101, 210), width=max(1, height // 82))

    # Fine parallel contours add depth while staying quiet at Wallet scale.
    for offset, alpha in ((10, 54), (18, 34), (27, 20)):
        contour = [(x, y + offset) for x, y in points]
        draw.line(contour, fill=(156, 87, 255, alpha), width=1)

    # Architectural gold arcs on the right edge create a recognizable luxury
    # signature and visually balance the single logo in the header.
    line_width = max(1, height // 80)
    base_left = round(width * 0.66)
    for index, alpha in enumerate((205, 138, 88, 50, 24)):
        expansion = index * max(8, height // 11)
        draw.arc(
            (
                base_left - expansion,
                -round(height * 1.10) - expansion,
                width + round(height * 0.82) + expansion,
                round(height * 1.86) + expansion,
            ),
            start=108,
            end=246,
            fill=(222, 171, 88, alpha),
            width=line_width,
        )

    # Subtle top sheen and bottom separator keep the artwork crisp on OLED.
    draw.line((round(width * 0.06), 1, round(width * 0.94), 1), fill=(255, 255, 255, 18), width=1)
    draw.line((round(width * 0.04), height - 2, round(width * 0.96), height - 2), fill=(235, 194, 118, 34), width=1)
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
        "foregroundColor": "rgb(250, 248, 252)",
        "backgroundColor": "rgb(4, 3, 8)",
        "labelColor": "rgb(232, 190, 111)",
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
        "logo.png": _png_bytes(_logo_image(160, 50)),
        "logo@2x.png": _png_bytes(_logo_image(320, 100)),
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
