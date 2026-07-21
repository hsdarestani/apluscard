from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.urls import reverse

from .models import Wallet


class SamsAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        is_apple_customer = SocialAccount.objects.filter(user=user, provider="apple").exists()
        if is_apple_customer and not Wallet.objects.filter(owner=user).exists() and not user.business_memberships.filter(is_active=True).exists():
            return reverse("complete_customer_profile")
        return reverse("dashboard")
