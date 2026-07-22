from django.shortcuts import redirect

from .models import Wallet


class CustomerLocationSelectionMiddleware:
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
        "/customer/standort-waehlen/",
        "/mitteilungen/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or request.path.startswith(self.exempt_prefixes):
            return self.get_response(request)
        if user.business_memberships.filter(is_active=True).exists():
            return self.get_response(request)

        wallet = Wallet.objects.filter(owner=user).select_related("business").first()
        if wallet is None:
            return self.get_response(request)
        selected = request.session.get("active_location_id")
        if selected and wallet.business.locations.filter(pk=selected, is_active=True).exists():
            return self.get_response(request)
        return redirect("customer_location_select")
