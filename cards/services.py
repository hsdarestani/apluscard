from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import AuditEvent, BusinessSettings, LedgerEntry, Membership, Offer, PaymentRequest, Wallet

OWNER_ROLES = {Membership.Role.OWNER}
MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
STAFF_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.STAFF}
CREDIT_TYPES = {LedgerEntry.Type.TOPUP, LedgerEntry.Type.REFUND, LedgerEntry.Type.BONUS}
DEBIT_TYPES = {LedgerEntry.Type.PURCHASE, LedgerEntry.Type.TIP}


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


def get_business_settings(business):
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=business)
    return settings_obj


def normalize_amount(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Ungültiger Betrag.") from exc
    if amount <= 0:
        raise ValidationError("Der Betrag muss größer als 0 sein.")
    return amount


def normalize_tip_amount(value):
    try:
        amount = Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Ungültige Trinkgeld-Auswahl.") from exc
    if amount < 0 or amount > Decimal("100.00"):
        raise ValidationError("Das Trinkgeld muss zwischen 0 und 100 Euro liegen.")
    return amount


def _month_start(moment=None):
    local = timezone.localtime(moment or timezone.now())
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def recalculate_wallet_tier(wallet, moment=None):
    settings_obj = get_business_settings(wallet.business)
    total = LedgerEntry.objects.filter(wallet=wallet, entry_type=LedgerEntry.Type.TOPUP, created_at__gte=_month_start(moment), amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if total >= settings_obj.platinum_threshold:
        tier = Wallet.Tier.PLATINUM
    elif total >= settings_obj.gold_threshold:
        tier = Wallet.Tier.GOLD
    else:
        tier = Wallet.Tier.SILVER
    Wallet.objects.filter(pk=wallet.pk).update(monthly_topup_total=total, tier=tier)
    wallet.monthly_topup_total = total
    wallet.tier = tier
    return wallet


def _assert_wallet_payable(wallet):
    if wallet.status != Wallet.Status.ACTIVE:
        raise ValidationError("Diese Karte ist nicht aktiv.")
    if wallet.owner_id:
        profile = getattr(wallet.owner, "member_profile", None)
        if profile and not profile.email_verified:
            raise ValidationError("Die E-Mail-Adresse des Members ist noch nicht bestätigt.")
        if profile and not profile.age_confirmed:
            raise ValidationError("Die Altersbestätigung des Members fehlt.")


@transaction.atomic
def post_wallet_entry(*, wallet, entry_type, amount, actor, description="", order_reference="", idempotency_key="", ip_address=None, location=None, payment_request=None):
    amount = normalize_amount(amount)
    locked_wallet = Wallet.objects.select_for_update().select_related("business").get(pk=wallet.pk)
    if entry_type in DEBIT_TYPES:
        _assert_wallet_payable(locked_wallet)
    elif locked_wallet.status != Wallet.Status.ACTIVE:
        raise ValidationError("Diese Karte ist nicht aktiv.")
    if location is not None and location.business_id != locked_wallet.business_id:
        raise ValidationError("Der ausgewählte Standort gehört nicht zu diesem Unternehmen.")
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
        business=locked_wallet.business,
        location=location,
        wallet=locked_wallet,
        payment_request=payment_request,
        entry_type=entry_type,
        amount=signed_amount,
        balance_before=before,
        balance_after=after,
        description=description.strip(),
        order_reference=order_reference.strip(),
        idempotency_key=idempotency_key.strip(),
        performed_by=actor,
    )
    AuditEvent.objects.create(
        actor=actor,
        business=locked_wallet.business,
        action=f"wallet.{entry_type.lower()}",
        object_type="wallet",
        object_id=str(locked_wallet.pk),
        ip_address=ip_address,
        details={
            "ledger_entry_id": str(entry.pk),
            "bill_number": entry.bill_number,
            "member_number": locked_wallet.member_number,
            "location_id": str(location.pk) if location else None,
            "payment_request_id": str(payment_request.pk) if payment_request else None,
            "amount": str(signed_amount),
            "balance_before": str(before),
            "balance_after": str(after),
            "order_reference": order_reference,
            "description": description,
        },
    )
    if entry_type == LedgerEntry.Type.TOPUP:
        recalculate_wallet_tier(locked_wallet)
    from .experience_services import notify_entry_posted
    notify_entry_posted(entry)
    return entry


@transaction.atomic
def create_payment_request(
    *,
    wallet,
    location,
    actor,
    amount,
    description="",
    order_reference="",
    tip_amount=Decimal("0.00"),
    tip_employee=None,
    ip_address=None,
    force_immediate=False,
    tip_percentage=None,
):
    """Create a charge. `tip_percentage` is accepted only as a legacy alias."""
    require_role(actor, wallet.business, STAFF_ROLES)
    if location.business_id != wallet.business_id or not location.is_active:
        raise ValidationError("Ungültiger Standort.")
    settings_obj = get_business_settings(wallet.business)
    amount = normalize_amount(amount)
    if tip_percentage is not None and tip_amount in (None, "", Decimal("0.00"), 0, "0"):
        tip_amount = tip_percentage
    selected_tip = normalize_tip_amount(tip_amount)
    allowed_tips = {normalize_tip_amount(value) for value in settings_obj.tip_options()}
    if selected_tip not in allowed_tips:
        raise ValidationError("Bitte einen der angebotenen Trinkgeldbeträge wählen.")
    payable_wallet = Wallet.objects.select_related("owner", "owner__member_profile").get(pk=wallet.pk)
    _assert_wallet_payable(payable_wallet)
    if payable_wallet.balance < amount + selected_tip:
        raise ValidationError("Nicht genügend Guthaben für Zahlung und Trinkgeld.")
    tip_recipient = settings_obj.tip_allocation
    if tip_recipient == BusinessSettings.TipAllocation.EMPLOYEE:
        tip_employee = tip_employee or actor
        if not get_active_membership(tip_employee, wallet.business):
            raise ValidationError("Der ausgewählte Mitarbeiter gehört nicht zu SAMS.")
    else:
        tip_employee = None
    confirmation_required = bool(settings_obj.require_customer_confirmation and not force_immediate)
    payment = PaymentRequest.objects.create(
        business=wallet.business,
        location=location,
        wallet=wallet,
        created_by=actor,
        base_amount=amount,
        tip_selected_amount=selected_tip,
        tip_recipient=tip_recipient,
        tip_employee=tip_employee,
        description=description.strip(),
        order_reference=order_reference.strip(),
        customer_confirmation_required=confirmation_required,
        expires_at=timezone.now() + timedelta(minutes=10) if confirmation_required else None,
    )
    if confirmation_required:
        from .experience_services import notify_payment_created
        notify_payment_created(payment)
    else:
        finalize_payment_request(payment=payment, confirmed_by=actor, tip_amount=selected_tip, ip_address=ip_address)
    return payment


@transaction.atomic
def finalize_payment_request(*, payment, confirmed_by, tip_amount=None, ip_address=None, tip_percentage=None):
    payment = PaymentRequest.objects.select_for_update().select_related("business", "location", "wallet").get(pk=payment.pk)
    if payment.status != PaymentRequest.Status.PENDING:
        raise ValidationError("Diese Zahlungsanfrage wurde bereits bearbeitet.")
    if payment.expires_at and payment.expires_at < timezone.now():
        payment.status = PaymentRequest.Status.EXPIRED
        payment.save(update_fields=["status"])
        raise ValidationError("Diese Zahlungsanfrage ist abgelaufen.")
    if payment.customer_confirmation_required and payment.wallet.owner_id != confirmed_by.id:
        raise PermissionDenied("Nur der betroffene Member kann diese Zahlung bestätigen.")
    settings_obj = get_business_settings(payment.business)
    if tip_amount is None:
        tip_amount = tip_percentage if tip_percentage is not None else payment.tip_selected_amount
    selected_tip = normalize_tip_amount(tip_amount)
    allowed = {normalize_tip_amount(value) for value in settings_obj.tip_options()}
    if selected_tip not in allowed:
        raise ValidationError("Bitte einen der angebotenen Trinkgeldbeträge wählen.")
    if payment.wallet.balance < payment.base_amount + selected_tip:
        raise ValidationError("Nicht genügend Guthaben für Zahlung und Trinkgeld.")
    purchase = post_wallet_entry(
        wallet=payment.wallet,
        location=payment.location,
        payment_request=payment,
        entry_type=LedgerEntry.Type.PURCHASE,
        amount=payment.base_amount,
        actor=payment.created_by,
        description=payment.description or f"Zahlung bei {payment.location.name}",
        order_reference=payment.order_reference,
        ip_address=ip_address,
    )
    tip_entry = None
    if selected_tip > 0:
        tip_description = "Trinkgeld für das Team"
        if payment.tip_employee_id:
            tip_description = f"Trinkgeld für {payment.tip_employee.get_full_name() or payment.tip_employee.username}"
        tip_entry = post_wallet_entry(
            wallet=payment.wallet,
            location=payment.location,
            payment_request=payment,
            entry_type=LedgerEntry.Type.TIP,
            amount=selected_tip,
            actor=payment.created_by,
            description=tip_description,
            order_reference=payment.order_reference,
            ip_address=ip_address,
        )
    payment.tip_selected_amount = selected_tip
    payment.tip_amount = selected_tip
    payment.purchase_entry = purchase
    payment.tip_entry = tip_entry
    payment.status = PaymentRequest.Status.CONFIRMED
    payment.confirmed_at = timezone.now()
    payment.save(update_fields=["tip_selected_amount", "tip_amount", "purchase_entry", "tip_entry", "status", "confirmed_at"])
    from .experience_services import notify_payment_finalized
    notify_payment_finalized(payment)
    AuditEvent.objects.create(
        actor=confirmed_by,
        business=payment.business,
        action="payment.confirmed",
        object_type="payment_request",
        object_id=str(payment.pk),
        ip_address=ip_address,
        details={
            "location_id": str(payment.location_id),
            "member_number": payment.wallet.member_number,
            "base_amount": str(payment.base_amount),
            "tip_amount": str(selected_tip),
            "tip_recipient": payment.tip_recipient,
            "tip_employee_id": payment.tip_employee_id,
        },
    )
    return payment


def active_offers_for(wallet, location=None, moment=None):
    now = moment or timezone.now()
    offers = Offer.objects.filter(business=wallet.business, is_active=True).filter(Q(target_tier=Offer.TargetTier.ALL) | Q(target_tier=wallet.tier))
    if location is not None:
        offers = offers.filter(Q(location__isnull=True) | Q(location=location))
    return offers.filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now)).select_related("location", "created_by")


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
