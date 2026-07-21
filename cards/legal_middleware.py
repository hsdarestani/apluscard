from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .legal_services import has_current_acceptances, wallet_for_customer


class LegalAcceptanceMiddleware:
    """Require customers to confirm the current per-app legal document versions."""

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
        "/manager/",
        "/staff/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)
        if request.path.startswith(self.exempt_prefixes):
            return self.get_response(request)
        if user.business_memberships.filter(is_active=True).exists():
            return self.get_response(request)

        wallet = wallet_for_customer(user)
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
