import base64
import hmac
import re
import time
from uuid import UUID

from django.conf import settings
from django.core import signing
from django.utils.crypto import salted_hmac

from .models import Wallet
from .qr_utils import qr_svg_data_uri

QR_PREFIX = "samsqr1."
QR_SIGNING_SALT = "sams-wallet-payment-qr-v1"
QR_SHORT_SIGNING_SALT = "sams-wallet-payment-qr-v2"
QR_BINARY_SIGNING_SALT = "sams-wallet-payment-qr-v3"
QR_BINARY_SIGNATURE_BYTES = 12
QR_BINARY_PAYLOAD_BYTES = 20
QR_BINARY_TOKEN_BYTES = QR_BINARY_PAYLOAD_BYTES + QR_BINARY_SIGNATURE_BYTES
SIGNED_TOKEN_PATTERN = re.compile(r"samsqr1\.[A-Za-z0-9_:\-.]+")
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)
MEMBER_NUMBER_PATTERN = re.compile(r"\d{3,12}")


def _effective_qr_max_age(max_age=None):
    if max_age is not None:
        return max_age
    return max(int(settings.WALLET_QR_MAX_AGE_SECONDS), 10 * 60)


def _b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value):
    try:
        raw = str(value or "").encode("ascii")
    except UnicodeEncodeError as exc:
        raise signing.BadSignature("Invalid SAMS QR encoding") from exc
    padding = b"=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(raw + padding)
    except (ValueError, TypeError) as exc:
        raise signing.BadSignature("Invalid SAMS QR encoding") from exc


def _binary_signature(payload):
    return salted_hmac(
        QR_BINARY_SIGNING_SALT,
        payload,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).digest()[:QR_BINARY_SIGNATURE_BYTES]


def issue_wallet_qr(wallet):
    """Issue the previous compact rotating token for backwards compatibility.

    Existing screenshots or older clients may still submit this format, so the
    resolver continues to accept it. The customer-facing QR no longer uses it:
    the app now displays the same static card UUID as Apple Wallet because that
    symbol has proven materially easier to scan phone-to-phone.
    """

    timestamp = int(time.time())
    payload = wallet.qr_token.bytes + timestamp.to_bytes(4, "big", signed=False)
    token = payload + _binary_signature(payload)
    return f"{QR_PREFIX}{_b64url_encode(token)}"


def wallet_qr_payload(wallet):
    """Render exactly the same card code used by Apple Wallet.

    Apple Wallet already exposes this UUID and the payment flow still requires an
    authenticated SAMS staff account plus explicit customer confirmation. Keeping
    the on-screen symbol static also prevents redraws while the cashier camera is
    trying to focus on another phone display.
    """

    token = str(wallet.qr_token)
    return {
        "token": token,
        "data_uri": qr_svg_data_uri(token),
        "expires_in": None,
        "refresh_in": 0,
        "static": True,
    }


def _extract_signed_token(raw_value):
    match = SIGNED_TOKEN_PATTERN.search(str(raw_value or "").strip())
    if match is None:
        raise signing.BadSignature("Signed SAMS QR token missing")
    return match.group(0)[len(QR_PREFIX):]


def _wallet_for_card_id(card_id, *, business=None):
    wallets = Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(
        qr_token=card_id,
        status=Wallet.Status.ACTIVE,
    )
    if business is not None:
        wallets = wallets.filter(business=business)
    return wallets.first()


def _active_wallet_from_static_code(raw_value, *, business=None):
    raw = str(raw_value or "").strip()
    if UUID_PATTERN.fullmatch(raw) is None:
        return None
    return _wallet_for_card_id(raw, business=business)


def _active_wallet_from_member_number(raw_value, *, business=None):
    """Allow the visible member number as the cashier's manual fallback."""

    if business is None:
        return None
    raw = str(raw_value or "").strip()
    if MEMBER_NUMBER_PATTERN.fullmatch(raw) is None:
        return None
    return Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(
        business=business,
        member_number=raw,
        status=Wallet.Status.ACTIVE,
    ).first()


def _resolve_binary_signed_token(signed_value, *, business=None, max_age=None):
    raw = _b64url_decode(signed_value)
    if len(raw) != QR_BINARY_TOKEN_BYTES:
        raise signing.BadSignature("Not a compact binary SAMS QR token")

    payload = raw[:QR_BINARY_PAYLOAD_BYTES]
    signature = raw[QR_BINARY_PAYLOAD_BYTES:]
    if not hmac.compare_digest(signature, _binary_signature(payload)):
        raise signing.BadSignature("Invalid SAMS QR signature")

    card_bytes = payload[:16]
    issued_at = int.from_bytes(payload[16:20], "big", signed=False)
    now = int(time.time())
    age = now - issued_at
    allowed_age = _effective_qr_max_age(max_age)
    if age < -60 or age > allowed_age:
        raise signing.SignatureExpired("SAMS QR token expired")

    card_id = UUID(bytes=card_bytes)
    wallet = _wallet_for_card_id(card_id, business=business)
    if wallet is None:
        raise signing.BadSignature("Wallet not found or inactive")
    return wallet


def _resolve_compact_signed_token(signed_value, *, business=None, max_age=None):
    raw_card_id = signing.TimestampSigner(salt=QR_SHORT_SIGNING_SALT).unsign(
        signed_value,
        max_age=_effective_qr_max_age(max_age),
    )
    try:
        card_id = UUID(str(raw_card_id))
    except (TypeError, ValueError) as exc:
        raise signing.BadSignature("Invalid SAMS QR card id") from exc
    wallet = _wallet_for_card_id(card_id, business=business)
    if wallet is None:
        raise signing.BadSignature("Wallet not found or inactive")
    return wallet


def _resolve_legacy_signed_token(signed_value, *, business=None, max_age=None):
    payload = signing.loads(
        signed_value,
        salt=QR_SIGNING_SALT,
        max_age=_effective_qr_max_age(max_age),
    )
    if payload.get("v") != 1:
        raise signing.BadSignature("Unsupported SAMS QR version")
    try:
        wallet_id = UUID(str(payload["wallet_id"]))
        card_id = UUID(str(payload["card_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise signing.BadSignature("Invalid SAMS QR payload") from exc

    wallets = Wallet.objects.select_related("business", "owner", "owner__member_profile").filter(
        pk=wallet_id,
        qr_token=card_id,
        status=Wallet.Status.ACTIVE,
    )
    if business is not None:
        wallets = wallets.filter(business=business)
    wallet = wallets.first()
    if wallet is None:
        raise signing.BadSignature("Wallet not found or inactive")
    return wallet


def resolve_payment_qr(raw_value, *, business=None, max_age=None):
    """Resolve app/Wallet UUID, current/legacy signed QR or member number."""

    signed_error = None
    try:
        signed_value = _extract_signed_token(raw_value)
    except signing.BadSignature as exc:
        signed_error = exc
    else:
        try:
            return _resolve_binary_signed_token(signed_value, business=business, max_age=max_age)
        except signing.BadSignature as binary_error:
            signed_error = binary_error

        try:
            return _resolve_compact_signed_token(signed_value, business=business, max_age=max_age)
        except signing.BadSignature as compact_error:
            signed_error = compact_error

        try:
            return _resolve_legacy_signed_token(signed_value, business=business, max_age=max_age)
        except signing.BadSignature:
            pass

    wallet = _active_wallet_from_static_code(raw_value, business=business)
    if wallet is not None:
        return wallet

    wallet = _active_wallet_from_member_number(raw_value, business=business)
    if wallet is not None:
        return wallet

    raise signed_error or signing.BadSignature("SAMS payment code not recognized")


def resolve_identity_qr(raw_value, *, business):
    try:
        return resolve_payment_qr(raw_value, business=business)
    except signing.BadSignature:
        return None
