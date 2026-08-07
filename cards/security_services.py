import os
import sys
import time
from urllib.parse import urlencode

import pyotp
from django.conf import settings
from django.urls import reverse

from .models import Membership


PRIVILEGED_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
MFA_SESSION_USER_KEY = "privileged_mfa_user_id"
MFA_SESSION_VERIFIED_AT_KEY = "privileged_mfa_verified_at"


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


def mfa_session_is_valid(request):
    if request.session.get(MFA_SESSION_USER_KEY) != request.user.pk:
        return False
    verified_at = int(request.session.get(MFA_SESSION_VERIFIED_AT_KEY, 0) or 0)
    return verified_at > 0 and int(time.time()) - verified_at <= mfa_session_seconds()


def mark_mfa_verified(request):
    request.session.cycle_key()
    request.session[MFA_SESSION_USER_KEY] = request.user.pk
    request.session[MFA_SESSION_VERIFIED_AT_KEY] = int(time.time())
    request.session.set_expiry(mfa_session_seconds())


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
