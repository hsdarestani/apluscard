from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import AppleProfileCompletionForm
from .models import Business, Wallet


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
            Wallet.objects.create(
                business=business,
                owner=user,
                display_name=name,
                phone=form.cleaned_data["phone"],
                email=user.email,
            )
            messages.success(request, "Dein Mitgliedskonto und deine digitale Mitgliedskarte sind jetzt bereit.")
            return redirect("customer_dashboard")
    else:
        form = AppleProfileCompletionForm(user=request.user)

    return render(request, "cards/complete_customer_profile.html", {"form": form})
