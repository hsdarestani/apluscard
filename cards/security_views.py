import base64
import io
import json
import time
from types import SimpleNamespace

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .models import AuditEvent, Business
from .security_models import PrivilegedMfaDevice
from .security_services import (
    biometric_device_token_is_valid,
    build_biometric_device_token,
    mark_mfa_verified,
    mfa_session_is_valid,
    privileged_membership,
    verify_totp_without_replay,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _safe_target(request, candidate, default="dashboard"):
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(default)


def _safe_next(request, default="dashboard"):
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    return _safe_target(request, candidate, default=default)


def _audit(request, membership, action, details=None):
    AuditEvent.objects.create(
        actor=request.user,
        business=membership.business,
        action=action,
        object_type="user",
        object_id=str(request.user.pk),
        details=details or {},
        ip_address=_client_ip(request),
    )


def _privileged_or_403(request):
    membership = privileged_membership(request.user)
    if membership is not None:
        return membership
    if not request.user.is_superuser:
        return None

    business = Business.objects.filter(is_active=True).order_by("pk").first()
    return SimpleNamespace(business=business) if business is not None else None


def _qr_data_uri(payload):
    image = qrcode.make(payload)
    output = io.BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _biometric_enrollment_requested(request):
    return (
        request.headers.get("X-SAMS-Biometric-Enroll", "") == "1"
        and "application/json" in request.headers.get("Accept", "")
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def mfa_setup(request):
    membership = _privileged_or_403(request)
    if membership is None:
        return HttpResponseForbidden("Diese Sicherheitsfunktion ist nur für Inhaber und Leitung verfügbar.")

    device, _ = PrivilegedMfaDevice.objects.get_or_create(user=request.user)
    if device.is_confirmed:
        if not mfa_session_is_valid(request):
            return redirect(f"{reverse('mfa_challenge')}?next={request.GET.get('next', '')}")
        return render(
            request,
            "cards/mfa_setup.html",
            {"device": device, "already_active": True, "next": _safe_next(request)},
        )

    secret = device.get_secret()
    if not secret:
        secret = pyotp.random_base32()
        device.set_secret(secret)
        device.last_counter = -1
        device.save(update_fields=["secret_encrypted", "last_counter", "updated_at"])

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=request.user.email or request.user.username,
        issuer_name=getattr(settings, "APP_NAME", "Sams Club Lounge"),
    )

    if request.method == "POST":
        candidate = request.POST.get("code", "").replace(" ", "")
        if totp.verify(candidate, valid_window=1):
            device.last_counter = int(time.time()) // totp.interval
            recovery_codes = PrivilegedMfaDevice.generate_recovery_codes()
            device.confirm(recovery_codes)
            mark_mfa_verified(request)
            _audit(request, membership, "mfa_enabled", {"recovery_codes_issued": len(recovery_codes)})
            return render(
                request,
                "cards/mfa_setup.html",
                {
                    "device": device,
                    "activated": True,
                    "recovery_codes": recovery_codes,
                    "next": _safe_next(request),
                },
            )
        _audit(request, membership, "mfa_setup_failed")
        messages.error(request, "Der sechsstellige Code ist ungültig. Bitte die Uhrzeit des Geräts prüfen und erneut versuchen.")

    return render(
        request,
        "cards/mfa_setup.html",
        {
            "device": device,
            "secret": secret,
            "qr_data_uri": _qr_data_uri(provisioning_uri),
            "next": _safe_next(request),
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def mfa_challenge(request):
    membership = _privileged_or_403(request)
    if membership is None:
        return HttpResponseForbidden("Diese Sicherheitsfunktion ist nur für Inhaber und Leitung verfügbar.")

    try:
        device = request.user.privileged_mfa_device
    except PrivilegedMfaDevice.DoesNotExist:
        return redirect(f"{reverse('mfa_setup')}?next={request.GET.get('next', '')}")
    if not device.is_confirmed:
        return redirect(f"{reverse('mfa_setup')}?next={request.GET.get('next', '')}")

    if mfa_session_is_valid(request):
        return redirect(_safe_next(request))

    if request.method == "POST":
        candidate = request.POST.get("code", "").strip()
        method = "totp"
        valid = verify_totp_without_replay(device, candidate)
        if not valid and "-" in candidate:
            method = "recovery"
            valid = device.consume_recovery_code(candidate)

        if valid:
            mark_mfa_verified(request)
            _audit(request, membership, "mfa_verified", {"method": method})
            target = _safe_next(request)
            if _biometric_enrollment_requested(request):
                token = build_biometric_device_token(request.user)
                return JsonResponse(
                    {
                        "ok": True,
                        "next": target,
                        "user_id": request.user.pk,
                        "biometric_token": token,
                    }
                )
            return redirect(target)

        _audit(request, membership, "mfa_verification_failed")
        detail = "Der Code ist ungültig, bereits verwendet oder abgelaufen."
        if _biometric_enrollment_requested(request):
            return JsonResponse({"ok": False, "detail": detail}, status=400)
        messages.error(request, detail)

    return render(
        request,
        "cards/mfa_challenge.html",
        {
            "next": _safe_next(request),
            "biometric_verify_url": reverse("mfa_biometric_verify"),
        },
    )


@login_required
@never_cache
@require_POST
def mfa_biometric_verify(request):
    """Renew privileged MFA after native Face ID/biometric verification.

    The native app stores an opaque server-signed credential in Keychain or
    Android Keystore. The JavaScript bridge only submits it after the operating
    system biometric prompt succeeds; the backend then validates account and
    MFA-device binding before renewing the privileged session.
    """

    membership = _privileged_or_403(request)
    if membership is None:
        return JsonResponse({"ok": False, "detail": "Nicht berechtigt."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "detail": "Ungültige Anfrage."}, status=400)

    token = str(payload.get("token") or "").strip()
    if not biometric_device_token_is_valid(request.user, token):
        _audit(request, membership, "mfa_biometric_failed")
        return JsonResponse(
            {
                "ok": False,
                "detail": "Dieses Gerät ist nicht mehr für die biometrische Bestätigung registriert.",
                "reenroll": True,
            },
            status=403,
        )

    mark_mfa_verified(request)
    _audit(request, membership, "mfa_verified", {"method": "biometric"})
    target = _safe_target(request, str(payload.get("next") or ""))
    return JsonResponse({"ok": True, "next": target})


@login_required
@never_cache
@require_POST
def mfa_regenerate_recovery_codes(request):
    membership = _privileged_or_403(request)
    if membership is None:
        return HttpResponseForbidden("Diese Sicherheitsfunktion ist nur für Inhaber und Leitung verfügbar.")

    try:
        device = request.user.privileged_mfa_device
    except PrivilegedMfaDevice.DoesNotExist:
        return redirect("mfa_setup")

    if not device.is_confirmed or not mfa_session_is_valid(request):
        return redirect(f"{reverse('mfa_challenge')}?next={reverse('mfa_setup')}")

    if not verify_totp_without_replay(device, request.POST.get("code", "")):
        _audit(request, membership, "mfa_recovery_regeneration_failed")
        messages.error(request, "Zur Erzeugung neuer Wiederherstellungscodes ist ein aktueller App-Code erforderlich.")
        return redirect("mfa_setup")

    recovery_codes = PrivilegedMfaDevice.generate_recovery_codes()
    device.replace_recovery_codes(recovery_codes)
    device.save(update_fields=["recovery_code_hashes", "updated_at"])
    _audit(request, membership, "mfa_recovery_codes_regenerated", {"count": len(recovery_codes)})
    return render(
        request,
        "cards/mfa_setup.html",
        {
            "device": device,
            "activated": True,
            "recovery_codes": recovery_codes,
            "next": reverse("manager_settings"),
        },
    )
