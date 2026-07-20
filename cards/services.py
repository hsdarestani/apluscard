from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import AuditEvent, LedgerEntry, Membership, Wallet


MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
STAFF_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.STAFF}
CREDIT_TYPES = {LedgerEntry.Type.TOPUP, LedgerEntry.Type.REFUND, LedgerEntry.Type.BONUS}
DEBIT_TYPES = {LedgerEntry.Type.PURCHASE}


def get_active_membership(user, business=None):
    memberships = Membership.objects.select_related("business").filter(user=user, is_active=True, business__is_active=True)
    if business is not None:
        memberships = memberships.filter(business=business)
    return memberships.first()


def require_role(user, business, allowed_roles):
    membership = get_active_membership(user, business)
    if not membership or membership.role not in allowed_roles:
        raise PermissionDenied("Keine Berechtigung für diese Aktion.")
    return membership


def normalize_amount(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Ungültiger Betrag.") from exc
    if amount <= 0:
        raise ValidationError("Der Betrag muss größer als 0 sein.")
    return amount


@transaction.atomic
def post_wallet_entry(*, wallet, entry_type, amount, actor, description="", order_reference="", idempotency_key="", ip_address=None):
    amount = normalize_amount(amount)
    locked_wallet = Wallet.objects.select_for_update().select_related("business").get(pk=wallet.pk)
    if locked_wallet.status != Wallet.Status.ACTIVE:
        raise ValidationError("Diese Karte ist nicht aktiv.")
    if entry_type in CREDIT_TYPES:
        signed_amount = amount
    elif entry_type in DEBIT_TYPES:
        signed_amount = -amount
    elif entry_type == LedgerEntry.Type.ADJUSTMENT:
        signed_amount = Decimal(str(amount))
    else:
        raise ValidationError("Unbekannter Transaktionstyp.")
    before = locked_wallet.balance
    after = before + signed_amount
    if after < 0:
        raise ValidationError("Nicht genügend Guthaben.")
    locked_wallet.balance = after
    locked_wallet.save(update_fields=["balance", "updated_at"])
    entry = LedgerEntry.objects.create(
        business=locked_wallet.business, wallet=locked_wallet, entry_type=entry_type, amount=signed_amount,
        balance_before=before, balance_after=after, description=description.strip(), order_reference=order_reference.strip(),
        idempotency_key=idempotency_key.strip(), performed_by=actor,
    )
    AuditEvent.objects.create(
        actor=actor, business=locked_wallet.business, action=f"wallet.{entry_type.lower()}", object_type="wallet",
        object_id=str(locked_wallet.pk), ip_address=ip_address,
        details={"ledger_entry_id": str(entry.pk), "amount": str(signed_amount), "balance_before": str(before), "balance_after": str(after), "order_reference": order_reference, "description": description},
    )
    return entry


@transaction.atomic
def set_wallet_status(*, wallet, status, actor, ip_address=None):
    locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    old_status = locked_wallet.status
    if status not in Wallet.Status.values:
        raise ValidationError("Ungültiger Kartenstatus.")
    locked_wallet.status = status
    locked_wallet.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(actor=actor, business=locked_wallet.business, action="wallet.status_changed", object_type="wallet", object_id=str(locked_wallet.pk), ip_address=ip_address, details={"from": old_status, "to": status})
    return locked_wallet
