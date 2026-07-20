import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Wallet
from .services import MANAGER_ROLES, get_active_membership


UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


@login_required
def manager_wallet_scan(request):
    """Resolve a scanned Member QR code within the manager's own business."""
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
        messages.error(request, "Diese Member Card gehört nicht zu dieser Lounge oder wurde nicht gefunden.")
        return redirect("manager_dashboard")

    return redirect("manager_wallet_detail", wallet_id=wallet.pk)
