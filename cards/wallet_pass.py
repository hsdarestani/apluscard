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


def _font(size):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _brand_image(width, height, *, compact=False):
    image = Image.new("RGBA", (width, height), (8, 5, 15, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=max(4, height // 5), fill=(8, 5, 15, 255))
    draw.ellipse((2, 2, height - 3, height - 3), fill=(122, 53, 255, 255))
    initials = "A+" if compact else "A+ CARD"
    draw.text((height + max(3, height // 8), height // 2), initials, fill=(255, 255, 255, 255), font=_font(max(9, height // 3)), anchor="lm")
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
        "description": f"Digitale {settings.APP_NAME} Mitgliedskarte",
        "logoText": "A+ CARD",
        "foregroundColor": "rgb(255, 255, 255)",
        "backgroundColor": "rgb(8, 5, 15)",
        "labelColor": "rgb(255, 180, 59)",
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
                {"key": "partner", "label": "PARTNER", "value": wallet.business.name},
                {"key": "locations", "label": "GÜLTIG", "value": "Alle drei Standorte"},
            ],
            "backFields": [
                {"key": "provider", "label": "Bereitgestellt von", "value": settings.APP_PUBLISHER},
                {"key": "usage", "label": "Verwendung", "value": "Diese digitale Mitgliedskarte gilt bei Sams Club Lounge, Sams Club Lounge CITY und DIMA Sportsbar."},
                {"key": "support", "label": "Support", "value": settings.APP_SUPPORT_EMAIL},
                {"key": "terms", "label": "AGB", "value": terms_url},
                {"key": "privacy", "label": "Datenschutz", "value": privacy_url},
                {"key": "deletion", "label": "Konto und Daten löschen", "value": delete_url},
            ],
        },
    }
    return {
        "pass.json": json.dumps(pass_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "icon.png": _png_bytes(_brand_image(29, 29, compact=True)),
        "icon@2x.png": _png_bytes(_brand_image(58, 58, compact=True)),
        "icon@3x.png": _png_bytes(_brand_image(87, 87, compact=True)),
        "logo.png": _png_bytes(_brand_image(160, 50)),
        "logo@2x.png": _png_bytes(_brand_image(320, 100)),
    }


def build_pkpass(wallet, request):
    if not settings.APPLE_WALLET_ENABLED:
        raise ImproperlyConfigured("Apple Wallet ist noch nicht mit einem Pass-Type-Zertifikat verbunden.")

    files = _pass_files(wallet, request)
    manifest = {
        filename: hashlib.sha1(content).hexdigest()
        for filename, content in files.items()
    }
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
