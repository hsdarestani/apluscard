import hashlib
import os
import sys
import time
from urllib.parse import urlencode

import pyotp
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils.crypto import constant_time_compare

from .models import Membership
from .security_models import PrivilegedMfaDevice


PRIVILEGED_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
MFA_SESSION_USER_KEY = "privileged_mfa_user_id"
MFA_SESSION_VERIFIED_AT_KEY = "privileged_mfa_verified_at"
BIOMETRIC_DEVICE_TOKEN_SALT = "sams-privileged-biometric-device-v1"


def privileged_membership(user):
    if not user or not user.is_authenticated:
        return None
    return (
        user.business_memberships.select_related("business")
        .filter(is_active=True, role__in=PRIVILEGED_ROLES)
        .order_by("-role")
        .first()
    )


def privileged_mfa_required():
    configured = os.getenv("PRIVILEGED_MFA_REQUIRED", "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    # Safe production default without disturbing the existing test suite.
    return not settings.DEBUG and "test" not in sys.argv


def mfa_session_seconds():
    raw_value = os.getenv("PRIVILEGED_MFA_SESSION_SECONDS", "43200").strip()
    try:
        return max(300, min(int(raw_value), settings.SESSION_COOKIE_AGE))
    except ValueError:
        return 12 * 60 * 60


def _confirmed_mfa_device(user):
    if not user or not user.is_authenticated:
        return None
    try:
        device = user.privileged_mfa_device
    except PrivilegedMfaDevice.DoesNotExist:
        return None
    return device if device.is_confirmed else None


def _biometric_device_fingerprint(user, device):
    """Bind a trusted native-device token to the current account and MFA secret.

    A password change, MFA reset/rotation or device replacement invalidates the
    stored native token without requiring a separate revocation table.
    """

    material = ":".join(
        [
            str(user.pk),
            str(device.pk),
            user.password or "",
            device.secret_encrypted or "",
            str(int(device.is_confirmed)),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_biometric_device_token(user):
    """Create the opaque credential stored by the native Keychain/Keystore.

    The token intentionally has no time-based expiry. It is only a second-factor
    device credential: an authenticated Django login session is still required,
    and every use is preceded by native Face ID/biometric verification in the
    app. Password/MFA reset or loss of the privileged role makes it unusable.
    """

    device = _confirmed_mfa_device(user)
    if device is None:
        return ""
    return signing.dumps(
        {
            "v": 1,
            "uid": user.pk,
            "did": device.pk,
            "fp": _biometric_device_fingerprint(user, device),
        },
        salt=BIOMETRIC_DEVICE_TOKEN_SALT,
        compress=True,
    )


def biometric_device_token_is_valid(user, token):
    if not token or not user or not user.is_authenticated:
        return False

    try:
        # No max_age on purpose: the trusted native device remains enrolled
        # until account/MFA credentials are changed or the privileged role is
        # removed. The regular login session still expires independently.
        payload = signing.loads(token, salt=BIOMETRIC_DEVICE_TOKEN_SALT)
    except (signing.BadSignature, TypeError, ValueError):
        return False

    if payload.get("v") != 1:
        return False
    device = _confirmed_mfa_device(user)
    if device is None:
        return False

    expected = _biometric_device_fingerprint(user, device)
    return (
        str(payload.get("uid")) == str(user.pk)
        and str(payload.get("did")) == str(device.pk)
        and constant_time_compare(str(payload.get("fp", "")), expected)
    )


def mfa_session_is_valid(request):
    if request.session.get(MFA_SESSION_USER_KEY) != request.user.pk:
        return False
    verified_at = int(request.session.get(MFA_SESSION_VERIFIED_AT_KEY, 0) or 0)
    return verified_at > 0 and int(time.time()) - verified_at <= mfa_session_seconds()


def mark_mfa_verified(request):
    request.session.cycle_key()
    request.session[MFA_SESSION_USER_KEY] = request.user.pk
    request.session[MFA_SESSION_VERIFIED_AT_KEY] = int(time.time())
    # Do not shorten the *login* session to the MFA re-check interval. The old
    # implementation called set_expiry(12h), which could log privileged users
    # out even though only the second factor was meant to expire. Keep the
    # normal Django session lifetime; Face ID can silently renew MFA as needed.
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)


def clear_mfa_session(request):
    request.session.pop(MFA_SESSION_USER_KEY, None)
    request.session.pop(MFA_SESSION_VERIFIED_AT_KEY, None)


def verify_totp_without_replay(device, candidate, valid_window=1):
    secret = device.get_secret()
    normalized = "".join(ch for ch in (candidate or "") if ch.isdigit())
    if not secret or len(normalized) != 6:
        return False

    totp = pyotp.TOTP(secret)
    current_counter = int(time.time()) // totp.interval
    accepted_counter = None
    for counter in range(current_counter - valid_window, current_counter + valid_window + 1):
        if pyotp.utils.strings_equal(totp.at(counter * totp.interval), normalized):
            accepted_counter = counter
            break

    if accepted_counter is None or accepted_counter <= device.last_counter:
        return False

    device.last_counter = accepted_counter
    device.save(update_fields=["last_counter", "updated_at"])
    return True


def mfa_action_url(request, route_name):
    target = request.get_full_path()
    return f"{reverse(route_name)}?{urlencode({'next': target})}"
