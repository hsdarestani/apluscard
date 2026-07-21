from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.apple.views import oauth2_callback as allauth_apple_callback
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import AppleProfileCompletionForm
from .models import Business, Wallet


@csrf_exempt
@require_POST
def apple_callback(request):
    """Receive Apple's cross-site form_post callback without CSRF failures.

    Apple posts the authorization response from appleid.apple.com. The OAuth
    state is still validated by django-allauth; only Django's form CSRF check is
    exempted for this dedicated callback. A stale or missing OAuth session is
    converted into a safe German retry instead of a raw 403 page.
    """
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
