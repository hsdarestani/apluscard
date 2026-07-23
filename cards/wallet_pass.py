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
from PIL import Image, ImageDraw, ImageFont


DARK = (8, 5, 14, 255)
PURPLE = (123, 45, 255, 255)
GOLD = (220, 167, 80, 255)
GOLD_LIGHT = (255, 211, 128, 255)
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
    draw.text((size / 2, size / 2), "S", font=_font(max(10, round(size * 0.48))), fill=WHITE, anchor="mm")
    return image


def _logo_image(width, height):
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    emblem = _icon_image(height)
    image.alpha_composite(emblem, (0, 0))
    x = height + max(5, height // 7)
    draw.text((x, height * 0.38), "SAMS", font=_font(max(12, height // 2)), fill=WHITE, anchor="lm")
    draw.text(
        (x, height * 0.76),
        "CLUB LOUNGE",
        font=_font(max(6, height // 7), bold=False),
        fill=GOLD_LIGHT,
        anchor="lm",
    )
    return image


def _strip_image(width, height):
    image = _vertical_gradient(width, height, (20, 10, 35, 255), DARK)
    glow_radius = round(height * 0.95)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (-glow_radius // 2, -glow_radius // 2, glow_radius, glow_radius),
        fill=(116, 38, 255, 150),
    )
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image)

    for offset, alpha in ((0, 120), (8, 70), (16, 35)):
        draw.arc(
            (round(width * 0.58) - offset, -round(height * 0.70) - offset, width + round(height * 0.55) + offset, round(height * 1.55) + offset),
            start=110,
            end=245,
            fill=(220, 167, 80, alpha),
            width=max(1, height // 45),
        )
    draw.text(
        (round(width * 0.065), round(height * 0.43)),
        "SAMS",
        font=_font(max(18, round(height * 0.28))),
        fill=WHITE,
        anchor="lm",
    )
    draw.text(
        (round(width * 0.068), round(height * 0.67)),
        "MEMBER CARD",
        font=_font(max(8, round(height * 0.085)), bold=False),
        fill=GOLD_LIGHT,
        anchor="lm",
    )
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
        "description": "Digitale SAMS Mitgliedskarte",
        "logoText": "SAMS",
        "foregroundColor": "rgb(255, 255, 255)",
        "backgroundColor": "rgb(8, 5, 14)",
        "labelColor": "rgb(255, 204, 112)",
        "sharingProhibited": True,
        "suppressStripShine": True,
        "barcodes": [barcode],
        "barcode": barcode,
        "storeCard": {
            "primaryFields": [
                {"key": "memberNumber", "label": "MITGLIEDSNUMMER", "value": wallet.member_number},
            ],
            "secondaryFields": [
                {"key": "memberName", "label": "MITGLIED", "value": wallet.display_name},
                {"key": "tier", "label": "STATUS", "value": wallet.get_tier_display()},
            ],
            "auxiliaryFields": [
                {"key": "validAt", "label": "GÜLTIG", "value": "Alle drei Standorte"},
            ],
            "backFields": [
                {"key": "partner", "label": "SAMS Standorte", "value": "Sams Club Lounge · Sams Club Lounge CITY · DIMA Sportsbar"},
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
