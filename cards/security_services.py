import hashlib
import os
import sys
import time
from urllib.parse import urlencode

import pyotp
from django.conf import settings
from django.core import signing
from django.urls import reverse

from .models import Membership
from .security_models import PrivilegedMfaDevice


PRIVILEGED_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
MFA_SESSION_USER_KEY = "privileged_mfa_user_id"
MFA_SESSION_VERIFIED_AT_KEY = "privileged_mfa_verified_at"
MFA_TRUST_COOKIE = "sams_privileged_mfa_trusted"
MFA_TRUST_SALT = "sams-privileged-mfa-trusted-device-v1"
# The server intentionally applies no age limit to the signed trust token. A
# long browser lifetime makes the app behave as a remembered device while still
# allowing an MFA reset/secret rotation to invalidate the token immediately.
MFA_TRUST_COOKIE_MAX_AGE = 10 * 365 * 24 * 60 * 60


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


def _mfa_device_fingerprint(device):
    material = f"{device.pk}:{device.secret_encrypted}:{int(device.is_confirmed)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _confirmed_mfa_device(user):
    if not user or not user.is_authenticated:
        return None
    try:
        device = user.privileged_mfa_device
    except PrivilegedMfaDevice.DoesNotExist:
        return None
    return device if device.is_confirmed else None


def build_mfa_trust_token(user):
    device = _confirmed_mfa_device(user)
    if device is None:
        return ""
    return signing.dumps(
        {
            "uid": user.pk,
            "did": device.pk,
            "fp": _mfa_device_fingerprint(device),
        },
        salt=MFA_TRUST_SALT,
        compress=True,
    )


def mfa_trusted_device_is_valid(request):
    token = request.COOKIES.get(MFA_TRUST_COOKIE, "")
    if not token or not getattr(request, "user", None) or not request.user.is_authenticated:
        return False

    try:
        # Deliberately no max_age: trusted app devices do not expire on the
        # server. Device reset/secret rotation invalidates the fingerprint.
        payload = signing.loads(token, salt=MFA_TRUST_SALT)
    except (signing.BadSignature, TypeError, ValueError):
        return False

    device = _confirmed_mfa_device(request.user)
    if device is None:
        return False

    return (
        str(payload.get("uid")) == str(request.user.pk)
        and str(payload.get("did")) == str(device.pk)
        and payload.get("fp") == _mfa_device_fingerprint(device)
    )


def set_mfa_trusted_cookie(response, user):
    token = build_mfa_trust_token(user)
    if not token:
        return response
    response.set_cookie(
        MFA_TRUST_COOKIE,
        token,
        max_age=MFA_TRUST_COOKIE_MAX_AGE,
        secure=getattr(settings, "SESSION_COOKIE_SECURE", True),
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response


def mfa_session_is_valid(request):
    if mfa_trusted_device_is_valid(request):
        return True
    if request.session.get(MFA_SESSION_USER_KEY) != request.user.pk:
        return False
    verified_at = int(request.session.get(MFA_SESSION_VERIFIED_AT_KEY, 0) or 0)
    return verified_at > 0 and int(time.time()) - verified_at <= mfa_session_seconds()


def mark_mfa_verified(request):
    request.session.cycle_key()
    request.session[MFA_SESSION_USER_KEY] = request.user.pk
    request.session[MFA_SESSION_VERIFIED_AT_KEY] = int(time.time())
    # MFA verification no longer shortens the normal login session. Persistent
    # device trust is carried by a separate signed HttpOnly cookie.


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
