import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.apple.views import oauth2_callback as allauth_apple_callback
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .apple_credentials import seal_apple_refresh_token
from .forms import AppleProfileCompletionForm
from .models import Business, Wallet


APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
_apple_jwk_client = jwt.PyJWKClient(APPLE_KEYS_URL, cache_keys=True)


class NativeAppleLoginError(Exception):
    pass


def _native_apple_client_id():
    return (getattr(settings, "APPLE_BUNDLE_ID", "") or settings.IOS_BUNDLE_ID).strip()


def _apple_client_secret(client_id):
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


def _exchange_apple_code(code, client_id):
    try:
        response = httpx.post(
            APPLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": _apple_client_secret(client_id),
                "code": code,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NativeAppleLoginError("Apple konnte die Anmeldung nicht bestätigen.") from exc

    if payload.get("error") or not payload.get("id_token"):
        raise NativeAppleLoginError("Der Apple-Anmeldecode ist ungültig oder abgelaufen.")
    return payload


def _decode_apple_identity_token(identity_token, client_id):
    try:
        signing_key = _apple_jwk_client.get_signing_key_from_jwt(identity_token)
        return jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=APPLE_ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise NativeAppleLoginError("Das Apple-Identitätstoken konnte nicht verifiziert werden.") from exc


def _verified_email(claims):
    email = str(claims.get("email") or "").strip().lower()
    verified = claims.get("email_verified")
    if isinstance(verified, str):
        verified = verified.lower() == "true"
    return email if email and verified is True else ""


def _unique_apple_username(apple_uid):
    User = get_user_model()
    base = f"apple_{hashlib.sha256(apple_uid.encode('utf-8')).hexdigest()[:24]}"
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


def _native_login_redirect(user):
    if Wallet.objects.filter(owner=user).exists() or user.business_memberships.filter(is_active=True).exists():
        return reverse("dashboard")
    return reverse("complete_customer_profile")


@csrf_exempt
@require_POST
def apple_callback(request):
    """Receive Apple's cross-site form_post callback without CSRF failures."""
    try:
        response = allauth_apple_callback(request)
    except PermissionDenied:
        messages.error(
            request,
            "Die Apple-Anmeldung konnte nicht abgeschlossen werden. Bitte starte sie erneut.",
        )
        return redirect("login")

    if getattr(response, "status_code", None) == 403:
        messages.error(
            request,
            "Die Apple-Anmeldung ist abgelaufen. Bitte starte sie erneut.",
        )
        return redirect("login")
    return response


@require_POST
def native_apple_login(request):
    """Create a Django session from a native AuthenticationServices result."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Ungültige Anmeldedaten."}, status=400)

    authorization_code = str(payload.get("authorizationCode") or "").strip()
    native_user = str(payload.get("user") or "").strip()
    nonce = str(payload.get("nonce") or "").strip()
    if not authorization_code or not native_user or not nonce:
        return JsonResponse({"ok": False, "error": "Die Apple-Anmeldung ist unvollständig."}, status=400)

    client_id = _native_apple_client_id()
    if not all(
        [
            client_id,
            settings.APPLE_KEY_ID,
            settings.APPLE_TEAM_ID,
            settings.APPLE_PRIVATE_KEY,
        ]
    ):
        return JsonResponse(
            {"ok": False, "error": "Die Apple-Anmeldung ist momentan nicht konfiguriert."},
            status=503,
        )

    try:
        token_payload = _exchange_apple_code(authorization_code, client_id)
        claims = _decode_apple_identity_token(token_payload["id_token"], client_id)
    except NativeAppleLoginError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    apple_uid = str(claims.get("sub") or "").strip()
    if not apple_uid or apple_uid != native_user:
        return JsonResponse({"ok": False, "error": "Die Apple-Identität stimmt nicht überein."}, status=400)
    if str(claims.get("nonce") or "") != nonce:
        return JsonResponse({"ok": False, "error": "Die Apple-Anmeldung konnte nicht eindeutig zugeordnet werden."}, status=400)

    email = _verified_email(claims)
    given_name = str(payload.get("givenName") or "").strip()[:150]
    family_name = str(payload.get("familyName") or "").strip()[:150]
    User = get_user_model()

    with transaction.atomic():
        social_account = SocialAccount.objects.select_related("user").filter(provider="apple", uid=apple_uid).first()
        if social_account is not None:
            user = social_account.user
        else:
            user = User.objects.filter(email__iexact=email).first() if email else None
            if user is None:
                if not email:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "Apple hat keine bestätigte E-Mail-Adresse übermittelt. Bitte prüfe deine Apple-ID-Einstellungen.",
                        },
                        status=400,
                    )
                user = User(username=_unique_apple_username(apple_uid), email=email)
                user.set_unusable_password()
                user.save()
            social_account = SocialAccount.objects.create(
                user=user,
                provider="apple",
                uid=apple_uid,
                extra_data={},
            )

        changed_fields = []
        if email and not user.email:
            user.email = email
            changed_fields.append("email")
        if given_name and not user.first_name:
            user.first_name = given_name
            changed_fields.append("first_name")
        if family_name and not user.last_name:
            user.last_name = family_name
            changed_fields.append("last_name")
        if changed_fields:
            user.save(update_fields=changed_fields)

        account_data = dict(social_account.extra_data or {})
        account_data.update(
            {
                "sub": apple_uid,
                "email": email or user.email,
                "email_verified": bool(email),
                "is_private_email": claims.get("is_private_email"),
                "real_user_status": payload.get("realUserStatus"),
            }
        )
        refresh_token = str(token_payload.get("refresh_token") or "").strip()
        if refresh_token:
            account_data["refresh_token_encrypted"] = seal_apple_refresh_token(refresh_token)
            account_data["refresh_token_client_id"] = client_id
        social_account.extra_data = account_data
        social_account.save(update_fields=["extra_data"])

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse({"ok": True, "redirect": _native_login_redirect(user)})


@login_required
@transaction.atomic
def complete_customer_profile(request):
    if request.user.business_memberships.filter(is_active=True).exists() or Wallet.objects.filter(owner=request.user).exists():
        return redirect("dashboard")

    if not SocialAccount.objects.filter(user=request.user, provider="apple").exists():
        messages.error(request, "Dieses Profil kann nur nach einer Anmeldung mit Apple vervollständigt werden.")
        return redirect("login")

    business = Business.objects.filter(slug=settings.DEFAULT_BUSINESS_SLUG, is_active=True).first()
    if business is None:
        messages.error(request, "Die Registrierung ist momentan nicht verfügbar. Bitte wende dich an das SAMS-Team.")
        return redirect("login")

    if request.method == "POST":
        form = AppleProfileCompletionForm(request.POST, user=request.user)
        if form.is_valid():
            user = form.save()
            name = f"{user.first_name} {user.last_name}".strip() or user.email
            wallet, _ = Wallet.objects.get_or_create(
                business=business,
                owner=user,
                defaults={
                    "display_name": name,
                    "phone": form.cleaned_data["phone"],
                    "email": user.email,
                },
            )
            if wallet.phone != form.cleaned_data["phone"] or wallet.display_name != name:
                wallet.phone = form.cleaned_data["phone"]
                wallet.display_name = name
                wallet.email = user.email
                wallet.save(update_fields=["phone", "display_name", "email", "updated_at"])
            messages.success(request, "Dein Mitgliedskonto und deine digitale Mitgliedskarte sind jetzt bereit.")
            return redirect("customer_dashboard")
    else:
        form = AppleProfileCompletionForm(user=request.user)

    return render(request, "cards/complete_customer_profile.html", {"form": form})
