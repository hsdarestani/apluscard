import re
from uuid import UUID

from django.conf import settings
from django.core import signing

from .models import Wallet
from .qr_utils import qr_data_uri

QR_PREFIX = "samsqr1."
QR_SIGNING_SALT = "sams-wallet-payment-qr-v1"
QR_SHORT_SIGNING_SALT = "sams-wallet-payment-qr-v2"
SIGNED_TOKEN_PATTERN = re.compile(r"samsqr1\.[A-Za-z0-9_:\-.]+")
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)
MEMBER_NUMBER_PATTERN = re.compile(r"\d{3,12}")


def _effective_qr_max_age(max_age=None):
    if max_age is not None:
        return max_age
    # Keep rotating QR codes short-lived, but give real-world cashier scans enough
    # time even when a WebView throttles the refresh timer or the customer needs a
    # moment to open the card. The payment still requires authenticated staff,
    # matching business scope, an active wallet and customer confirmation.
    return max(int(settings.WALLET_QR_MAX_AGE_SECONDS), 10 * 60)


def issue_wallet_qr(wallet):
    """Issue a compact rotating payment token.

    Older versions embedded two UUIDs inside a signed JSON payload. That produced
    a very dense QR code on smaller phone screens. The current format signs only
    the card UUID with a timestamp, while keeping the public prefix unchanged so
    existing scanner clients do not need an app update.
    """

    signed = signing.TimestampSigner(salt=QR_SHORT_SIGNING_SALT).sign(str(wallet.qr_token))
    return f"{QR_PREFIX}{signed}"


def wallet_qr_payload(wallet):
    token = issue_wallet_qr(wallet)
    return {
        "token": token,
        "data_uri": qr_data_uri(token),
        "expires_in": _effective_qr_max_age(),
        "refresh_in": settings.WALLET_QR_REFRESH_SECONDS,
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
    """Allow the visible member number as the cashier's manual fallback.

    Member numbers are scoped to a business. We deliberately do not resolve a
    bare member number without business context to avoid ambiguity across tenants.
    """

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
    """Resolve rotating app QR, legacy rotating QR, Apple Wallet code or member number."""

    signed_error = None
    try:
        signed_value = _extract_signed_token(raw_value)
    except signing.BadSignature as exc:
        signed_error = exc
    else:
        try:
            return _resolve_compact_signed_token(signed_value, business=business, max_age=max_age)
        except signing.BadSignature as compact_error:
            signed_error = compact_error
            try:
                return _resolve_legacy_signed_token(signed_value, business=business, max_age=max_age)
            except signing.BadSignature:
                pass

    # Static Apple Wallet codes are accepted only when the complete value is a
    # UUID. This prevents an expired compact token (which contains a UUID inside
    # the signed string) from bypassing the timestamp check.
    wallet = _active_wallet_from_static_code(raw_value, business=business)
    if wallet is not None:
        return wallet

    wallet = _active_wallet_from_member_number(raw_value, business=business)
    if wallet is not None:
        return wallet

    raise signed_error or signing.BadSignature("SAMS payment code not recognized")


def resolve_identity_qr(raw_value, *, business):
    """Resolve either a rotating app QR or a static Apple Wallet/member QR."""

    try:
        return resolve_payment_qr(raw_value, business=business)
    except signing.BadSignature:
        return None
