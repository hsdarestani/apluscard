import base64
import hashlib
import json
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


DARK = (6, 3, 11, 255)
DARK_PURPLE = (28, 7, 40, 255)
PURPLE = (133, 38, 244, 255)
PINK = (235, 47, 171, 255)
GOLD = (220, 167, 80, 255)
GOLD_LIGHT = (255, 218, 148, 255)
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

    image = _vertical_gradient(size, size, (13, 8, 22, 255), (4, 3, 8, 255))
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
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    icon_size = min(height, 42 if height >= 42 else height)
    emblem = _icon_image(icon_size)
    image.alpha_composite(emblem, (0, round((height - icon_size) / 2)))
    return image


def _strip_image(width, height):
    """Premium, quiet Wallet background with subtle SAMS light signatures."""
    image = _vertical_gradient(width, height, DARK_PURPLE, DARK)

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (-round(width * .20), -round(height * .85), round(width * .58), round(height * 1.55)),
        fill=(139, 34, 244, 105),
    )
    glow_draw.ellipse(
        (round(width * .48), -round(height * .75), round(width * 1.10), round(height * 1.20)),
        fill=(235, 47, 171, 55),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(max(12, height // 7)))
    image = Image.alpha_composite(image, glow)

    draw = ImageDraw.Draw(image)
    line_width = max(2, height // 55)
    for x_offset, alpha in ((0, 170), (10, 90), (21, 40)):
        draw.arc(
            (
                round(width * .62) - x_offset,
                -round(height * .95) - x_offset,
                width + round(height * .70) + x_offset,
                round(height * 1.70) + x_offset,
            ),
            start=112,
            end=244,
            fill=(220, 167, 80, alpha),
            width=line_width,
        )

    draw.line((round(width * .07), height - 2, round(width * .93), height - 2), fill=(255, 255, 255, 20), width=1)
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
        "altText": f"Mitglied {wallet.member_number}",
    }
    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": settings.APPLE_WALLET_PASS_TYPE_ID,
        "serialNumber": str(wallet.pk),
        "teamIdentifier": settings.APPLE_WALLET_TEAM_ID,
        "organizationName": settings.APP_PUBLISHER,
        "description": "Digitale Sams Club Lounge Mitgliedskarte",
        "logoText": "SCL",
        "foregroundColor": "rgb(255, 255, 255)",
        "backgroundColor": "rgb(6, 3, 11)",
        "labelColor": "rgb(255, 211, 128)",
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
        "thumbnail.png": _png_bytes(_icon_image(90)),
        "thumbnail@2x.png": _png_bytes(_icon_image(180)),
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
