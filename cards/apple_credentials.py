import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from allauth.socialaccount.models import SocialAccount
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
APPLE_ISSUER = "https://appleid.apple.com"


def _fernet():
    digest = hashlib.sha256(f"{settings.SECRET_KEY}:apple-refresh-token".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal_apple_refresh_token(token):
    """Encrypt an Apple refresh token before persisting it in SocialAccount.extra_data."""
    value = str(token or "").strip()
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def _open_apple_refresh_token(token):
    try:
        return _fernet().decrypt(str(token).encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise ValueError("Apple refresh token could not be decrypted") from exc


def _client_secret(client_id):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": settings.APPLE_TEAM_ID,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "aud": APPLE_ISSUER,
            "sub": client_id,
        },
        settings.APPLE_PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": settings.APPLE_KEY_ID},
    )


def revoke_apple_credentials(user):
    """Revoke a stored Sign in with Apple refresh token during account deletion.

    Account deletion must continue even for legacy accounts that predate refresh-token
    storage. The returned status is written to the deletion audit note.
    """
    if user is None:
        return "not_applicable"

    social_account = SocialAccount.objects.filter(user=user, provider="apple").first()
    if social_account is None:
        return "not_applicable"

    extra_data = dict(social_account.extra_data or {})
    encrypted_token = str(extra_data.get("refresh_token_encrypted") or "").strip()
    if not encrypted_token:
        return "legacy_token_unavailable"

    client_id = str(
        extra_data.get("refresh_token_client_id")
        or getattr(settings, "APPLE_BUNDLE_ID", "")
        or settings.IOS_BUNDLE_ID
    ).strip()
    if not all(
        [
            client_id,
            settings.APPLE_KEY_ID,
            settings.APPLE_TEAM_ID,
            settings.APPLE_PRIVATE_KEY,
        ]
    ):
        logger.error("Apple credential revocation is not configured for user_id=%s", user.pk)
        return "configuration_missing"

    try:
        refresh_token = _open_apple_refresh_token(encrypted_token)
        response = httpx.post(
            APPLE_REVOKE_URL,
            data={
                "client_id": client_id,
                "client_secret": _client_secret(client_id),
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            },
            headers={"Accept": "application/json"},
            timeout=12,
        )
        response.raise_for_status()
    except (ValueError, httpx.HTTPError, jwt.PyJWTError):
        logger.exception("Apple credential revocation failed for user_id=%s", user.pk)
        return "failed"

    extra_data.pop("refresh_token_encrypted", None)
    extra_data.pop("refresh_token_client_id", None)
    social_account.extra_data = extra_data
    social_account.save(update_fields=["extra_data"])
    logger.info("Apple credentials revoked for user_id=%s", user.pk)
    return "revoked"
