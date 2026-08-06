from allauth.socialaccount.models import SocialAccount
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .legal_services import has_current_acceptances, wallet_for_customer
from .security_models import PrivilegedMfaDevice
from .security_services import (
    mfa_action_url,
    mfa_session_is_valid,
    privileged_membership,
    privileged_mfa_required,
)


class LegalAcceptanceMiddleware:
    """Enforce privileged MFA and current per-app legal document versions."""

    mfa_exempt_prefixes = (
        "/static/",
        "/media/",
        "/health/",
        "/manifest.webmanifest",
        "/sw.js",
        "/accounts/",
        "/sicherheit/2fa/",
        "/agb/",
        "/datenschutz/",
        "/impressum/",
        "/apps/",
        "/wallet/download/",
    )

    exempt_prefixes = (
        "/admin/",
        "/static/",
        "/media/",
        "/health/",
        "/manifest.webmanifest",
        "/sw.js",
        "/accounts/",
        "/sicherheit/2fa/",
        "/agb/",
        "/datenschutz/",
        "/impressum/",
        "/apps/",
        "/rechtliches-bestaetigen/",
        "/wallet/download/",
        "/manager/",
        "/staff/",
    )

    # A newly authenticated Apple user does not have a Wallet until the final
    # onboarding form is submitted. App Review may navigate away from that form
    # before completion, so every protected destination must route back to the
    # onboarding step instead of exposing Django's raw 403 response.
    onboarding_exempt_prefixes = (
        "/admin/",
        "/static/",
        "/media/",
        "/health/",
        "/manifest.webmanifest",
        "/sw.js",
        "/accounts/",
        "/sicherheit/2fa/",
        "/agb/",
        "/impressum/",
        "/apps/",
        "/wallet/download/",
    )
    onboarding_exempt_paths = (
        "/datenschutz/",
        "/datenschutz/konto-loeschen/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_api_request(request):
        return request.path.startswith("/api/") or "application/json" in request.headers.get("Accept", "")

    def _enforce_privileged_mfa(self, request):
        if not privileged_mfa_required():
            return None

        membership = privileged_membership(request.user)
        if membership is None and not request.user.is_superuser:
            return None
        if request.path.startswith(self.mfa_exempt_prefixes):
            return None

        try:
            device = request.user.privileged_mfa_device
        except PrivilegedMfaDevice.DoesNotExist:
            device = None

        route_name = "mfa_setup" if device is None or not device.is_confirmed else "mfa_challenge"
        if device is not None and device.is_confirmed and mfa_session_is_valid(request):
            return None

        action_url = mfa_action_url(request, route_name)
        if self._is_api_request(request):
            return JsonResponse(
                {
                    "detail": "Für Inhaber und Leitung ist eine Zwei-Faktor-Bestätigung erforderlich.",
                    "action_url": action_url,
                },
                status=428,
            )
        return redirect(action_url)

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        mfa_response = self._enforce_privileged_mfa(request)
        if mfa_response is not None:
            return mfa_response

        has_business_membership = user.business_memberships.filter(is_active=True).exists()
        wallet = None if has_business_membership else wallet_for_customer(user)

        incomplete_apple_onboarding = (
            not has_business_membership
            and wallet is None
            and SocialAccount.objects.filter(user=user, provider="apple").exists()
        )
        if incomplete_apple_onboarding:
            path = request.path
            if path in self.onboarding_exempt_paths or path.startswith(self.onboarding_exempt_prefixes):
                return self.get_response(request)

            action_url = reverse("complete_customer_profile")
            if self._is_api_request(request):
                return JsonResponse(
                    {
                        "detail": "Bitte schließe zuerst die Einrichtung deines Mitgliedskontos ab.",
                        "action_url": action_url,
                    },
                    status=409,
                )
            return redirect(action_url)

        if request.path.startswith(self.exempt_prefixes):
            return self.get_response(request)
        if has_business_membership:
            return self.get_response(request)

        if not wallet or has_current_acceptances(user, wallet.business):
            return self.get_response(request)

        if request.path.startswith("/api/"):
            return JsonResponse(
                {
                    "detail": "Bitte bestätige zuerst die aktuellen AGB und Datenschutzhinweise.",
                    "action_url": reverse("legal_acceptance"),
                },
                status=428,
            )
        return redirect("legal_acceptance")
