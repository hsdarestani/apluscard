from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse

from .models import Wallet


class SamsAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        has_wallet = Wallet.objects.filter(owner=user).exists()
        has_business_access = user.business_memberships.filter(is_active=True).exists()

        # During the first Apple login, the SocialAccount row can still be part
        # of the surrounding allauth transaction when this redirect is chosen.
        # Therefore the decision must be based on the actual SAMS account state,
        # not on whether the Apple row is already visible in a second query.
        if not has_wallet and not has_business_access:
            return reverse("complete_customer_profile")
        return reverse("dashboard")
