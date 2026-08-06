from allauth.socialaccount.models import SocialAccount
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .legal_services import has_current_acceptances, wallet_for_customer
from .models import Membership


class LegalAcceptanceMiddleware:
    """Require current legal acceptance and enforce a minimal staff workspace."""

    exempt_prefixes = (
        "/admin/",
        "/static/",
        "/media/",
        "/health/",
        "/manifest.webmanifest",
        "/sw.js",
        "/accounts/",
        "/agb/",
        "/datenschutz/",
        "/impressum/",
        "/apps/",
        "/rechtliches-bestaetigen/",
        "/wallet/download/",
        "/manager/",
        "/staff/",
    )

    staff_allowed_prefixes = (
        "/static/",
        "/media/",
        "/health/",
        "/manifest.webmanifest",
        "/sw.js",
        "/app-icon-",
        "/staff/",
        "/location/select/",
        "/api/v1/staff/charge/",
        "/accounts/logout/",
    )

    onboarding_exempt_prefixes = (
        "/admin/",
        "/static/",
        "/media/",
        "/health/",
        "/manifest.webmanifest",
        "/sw.js",
        "/accounts/",
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

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        membership = (
            user.business_memberships.select_related("business")
            .filter(is_active=True, business__is_active=True)
            .first()
        )
        has_business_membership = membership is not None

        if membership and membership.role == Membership.Role.STAFF:
            if request.path.startswith(self.staff_allowed_prefixes):
                return self.get_response(request)
            if request.path.startswith("/api/") or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse(
                    {"detail": "Mitarbeiterkonten dürfen ausschließlich Zahlungen scannen und abbuchen."},
                    status=403,
                )
            return redirect("staff_dashboard")

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
            if path.startswith("/api/") or "application/json" in request.headers.get("Accept", ""):
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
