import logging
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .emailing import send_verification_email
from .models import Wallet
from .services import MANAGER_ROLES, get_active_membership


logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


@login_required
def manager_wallet_scan(request):
    """Eine gescannte Mitgliedskarte innerhalb des eigenen Betriebs auflösen."""
    membership = get_active_membership(request.user)
    if not membership or membership.role not in MANAGER_ROLES:
        raise PermissionDenied

    raw_value = request.GET.get("token", "").strip()
    match = UUID_PATTERN.search(raw_value)
    if match is None:
        messages.error(request, "Der QR-Code enthält keinen gültigen Kartencode.")
        return redirect("manager_dashboard")

    wallet = Wallet.objects.filter(
        business=membership.business,
        qr_token=match.group(0),
    ).first()
    if wallet is None:
        messages.error(request, "Diese Mitgliedskarte gehört nicht zu diesem Betrieb oder wurde nicht gefunden.")
        return redirect("manager_dashboard")

    return redirect("manager_wallet_detail", wallet_id=wallet.pk)


@login_required
@require_POST
def manager_resend_verification(request, wallet_id):
    """Resend a tracked confirmation link from the normal manager wallet page."""
    wallet = get_object_or_404(
        Wallet.objects.select_related("business", "owner", "owner__member_profile"),
        pk=wallet_id,
    )
    membership = get_active_membership(request.user)
    if (
        not membership
        or membership.role not in MANAGER_ROLES
        or membership.business_id != wallet.business_id
    ):
        raise PermissionDenied

    if wallet.owner is None:
        messages.error(request, "Diese Mitgliedskarte ist keinem Benutzerkonto zugeordnet.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    profile = getattr(wallet.owner, "member_profile", None)
    if profile is None:
        messages.error(request, "Für dieses Benutzerkonto fehlt das Mitgliederprofil.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    if profile.email_verified:
        messages.info(request, "Die E-Mail-Adresse dieses Mitglieds ist bereits bestätigt.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    if not (wallet.owner.email or "").strip():
        messages.error(request, "Für dieses Mitglied ist keine E-Mail-Adresse hinterlegt.")
        return redirect("manager_wallet_detail", wallet_id=wallet.pk)

    try:
        send_verification_email(request, wallet.owner)
    except Exception:
        logger.exception(
            "Manager verification resend failed manager_id=%s wallet_id=%s user_id=%s",
            request.user.pk,
            wallet.pk,
            wallet.owner_id,
        )
        messages.error(
            request,
            "Die Bestätigungs-E-Mail konnte nicht versendet werden. Der Fehler wurde protokolliert.",
        )
    else:
        messages.success(
            request,
            f"Ein neuer Bestätigungslink wurde an {wallet.owner.email} versendet.",
        )

    return redirect("manager_wallet_detail", wallet_id=wallet.pk)
