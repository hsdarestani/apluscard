import re
from uuid import UUID

from django.conf import settings
from django.core import signing

from .models import Wallet
from .qr_utils import qr_data_uri

QR_PREFIX = "samsqr1."
QR_SIGNING_SALT = "sams-wallet-payment-qr-v1"
SIGNED_TOKEN_PATTERN = re.compile(r"samsqr1\.[A-Za-z0-9_:\-.]+")
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def issue_wallet_qr(wallet):
    payload = {
        "v": 1,
        "wallet_id": str(wallet.pk),
        "card_id": str(wallet.qr_token),
    }
    signed = signing.dumps(payload, salt=QR_SIGNING_SALT, compress=True)
    return f"{QR_PREFIX}{signed}"


def wallet_qr_payload(wallet):
    token = issue_wallet_qr(wallet)
    return {
        "token": token,
        "data_uri": qr_data_uri(token),
        "expires_in": settings.WALLET_QR_MAX_AGE_SECONDS,
        "refresh_in": settings.WALLET_QR_REFRESH_SECONDS,
    }


def _extract_signed_token(raw_value):
    match = SIGNED_TOKEN_PATTERN.search(str(raw_value or "").strip())
    if match is None:
        raise signing.BadSignature("Signed SAMS QR token missing")
    return match.group(0)[len(QR_PREFIX):]


def resolve_payment_qr(raw_value, *, business=None, max_age=None):
    """Resolve a short-lived payment QR and reject static copied card UUIDs."""

    signed_value = _extract_signed_token(raw_value)
    payload = signing.loads(
        signed_value,
        salt=QR_SIGNING_SALT,
        max_age=max_age or settings.WALLET_QR_MAX_AGE_SECONDS,
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


def resolve_identity_qr(raw_value, *, business):
    """Resolve either a rotating payment QR or a static membership-card UUID.

    Static codes are accepted only for opening the member record. Payment
    endpoints call resolve_payment_qr() and therefore reject screenshots or old
    Apple Wallet barcodes.
    """

    try:
        return resolve_payment_qr(raw_value, business=business)
    except signing.BadSignature:
        match = UUID_PATTERN.search(str(raw_value or "").strip())
        if match is None:
            return None
        return Wallet.objects.filter(
            business=business,
            qr_token=match.group(0),
        ).first()
