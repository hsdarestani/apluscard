from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from .experience_models import TransactionCase
from .models import AppNotification, AuditEvent, LedgerEntry, Membership, Offer, Wallet
from .services import MANAGER_ROLES, OWNER_ROLES, STAFF_ROLES, get_active_membership, normalize_amount, post_wallet_entry, require_role


def _unique_users(users):
    unique = {}
    for user in users:
        if user and user.pk:
            unique[user.pk] = user
    return list(unique.values())


def create_notifications(*, users, business, title, body, kind=AppNotification.Kind.SYSTEM, location=None, data=None):
    users = _unique_users(users)
    if not users:
        return []
    notifications = [
        AppNotification(
            recipient=user,
            business=business,
            location=location,
            kind=kind,
            title=title,
            body=body,
            data=data or {},
        )
        for user in users
    ]
    return AppNotification.objects.bulk_create(notifications)


def management_users(business):
    return [
        item.user
        for item in Membership.objects.filter(
            business=business,
            role__in=MANAGER_ROLES,
            is_active=True,
        ).select_related("user")
    ]


def notify_entry_posted(entry):
    customer = entry.wallet.owner
    if customer is None:
        return
    labels = {
        LedgerEntry.Type.TOPUP: "Guthaben aufgeladen",
        LedgerEntry.Type.REFUND: "Betrag erstattet",
        LedgerEntry.Type.BONUS: "Bonus erhalten",
        LedgerEntry.Type.ADJUSTMENT: "Guthaben korrigiert",
    }
    title = labels.get(entry.entry_type)
    if not title:
        return
    create_notifications(
        users=[customer],
        business=entry.business,
        location=entry.location,
        kind=AppNotification.Kind.PAYMENT,
        title=title,
        body=f"{abs(entry.amount):.2f} € · Neuer Kontostand {entry.balance_after:.2f} €.",
        data={
            "url": reverse("bill_detail", args=[entry.pk]),
            "ledger_entry_id": str(entry.pk),
            "bill_number": entry.bill_number,
        },
    )


def notify_payment_created(payment):
    if not payment.wallet.owner_id:
        return
    create_notifications(
        users=[payment.wallet.owner],
        business=payment.business,
        location=payment.location,
        kind=AppNotification.Kind.PAYMENT,
        title="Zahlung wartet auf Bestätigung",
        body=f"{payment.base_amount:.2f} € bei {payment.location.name}. Bitte Trinkgeld wählen und Zahlung bestätigen.",
        data={
            "url": reverse("customer_dashboard"),
            "payment_request_id": str(payment.pk),
        },
    )


def notify_payment_finalized(payment):
    recipients = management_users(payment.business)
    recipients.extend([payment.wallet.owner, payment.created_by])
    create_notifications(
        users=recipients,
        business=payment.business,
        location=payment.location,
        kind=AppNotification.Kind.PAYMENT,
        title="A+ Pay Zahlung abgeschlossen",
        body=f"{payment.wallet.display_name} · {payment.base_amount:.2f} € + {payment.tip_amount:.2f} € Trinkgeld · {payment.location.name}.",
        data={
            "url": reverse("bill_detail", args=[payment.purchase_entry_id]),
            "payment_request_id": str(payment.pk),
            "wallet_id": str(payment.wallet_id),
            "member_number": payment.wallet.member_number,
        },
    )


def notify_offer_audience(offer):
    wallets = Wallet.objects.filter(
        business=offer.business,
        owner__isnull=False,
        status=Wallet.Status.ACTIVE,
    ).select_related("owner")
    if offer.target_tier != Offer.TargetTier.ALL:
        wallets = wallets.filter(tier=offer.target_tier)
    users = [wallet.owner for wallet in wallets]
    create_notifications(
        users=users,
        business=offer.business,
        location=offer.location,
        kind=AppNotification.Kind.OFFER,
        title=offer.title,
        body=(offer.body[:180] + "…") if len(offer.body) > 180 else offer.body,
        data={
            "url": reverse("customer_dashboard") + "#offers",
            "offer_id": str(offer.pk),
        },
    )


def _opened_by_role(entry, user):
    if entry.wallet.owner_id == user.id:
        return TransactionCase.OpenedByRole.CUSTOMER
    membership = get_active_membership(user, entry.business)
    if membership and membership.role in STAFF_ROLES and entry.performed_by_id == user.id:
        return TransactionCase.OpenedByRole.STAFF
    raise PermissionDenied("Du darfst für diese Transaktion keinen Fall eröffnen.")


@transaction.atomic
def create_transaction_case(*, entry, opened_by, reason, description, requested_amount=None, ip_address=None):
    role = _opened_by_role(entry, opened_by)
    if TransactionCase.objects.filter(
        ledger_entry=entry,
        opened_by=opened_by,
        status__in=[TransactionCase.Status.OPEN, TransactionCase.Status.IN_REVIEW],
    ).exists():
        raise ValidationError("Für diese Transaktion ist bereits ein offener Fall vorhanden.")

    amount = None
    if requested_amount not in (None, ""):
        amount = normalize_amount(requested_amount)
        if entry.amount >= 0:
            raise ValidationError("Für diese Buchung ist keine automatische Erstattung möglich.")
        if amount > abs(entry.amount):
            raise ValidationError("Der gewünschte Betrag überschreitet die ursprüngliche Belastung.")

    transaction_case = TransactionCase.objects.create(
        business=entry.business,
        location=entry.location,
        wallet=entry.wallet,
        ledger_entry=entry,
        opened_by=opened_by,
        opened_by_role=role,
        reason=reason,
        description=description.strip(),
        requested_amount=amount,
    )
    case_url = reverse("transaction_case_detail", args=[transaction_case.pk])
    create_notifications(
        users=management_users(entry.business),
        business=entry.business,
        location=entry.location,
        title="Neuer Transaktionsfall",
        body=f"{transaction_case.case_number} · {transaction_case.get_reason_display()} · Mitglied {entry.wallet.member_number}.",
        data={"url": case_url, "transaction_case_id": str(transaction_case.pk)},
    )
    create_notifications(
        users=[opened_by],
        business=entry.business,
        location=entry.location,
        title="Transaktionsfall eingereicht",
        body=f"{transaction_case.case_number} wurde zur Prüfung an die Verwaltung gesendet.",
        data={"url": case_url, "transaction_case_id": str(transaction_case.pk)},
    )
    AuditEvent.objects.create(
        actor=opened_by,
        business=entry.business,
        action="transaction_case.created",
        object_type="transaction_case",
        object_id=str(transaction_case.pk),
        ip_address=ip_address,
        details={
            "case_number": transaction_case.case_number,
            "ledger_entry_id": str(entry.pk),
            "opened_by_role": role,
            "requested_amount": str(amount) if amount else None,
        },
    )
    return transaction_case


@transaction.atomic
def review_transaction_case(*, transaction_case, reviewer, action, manager_note="", approved_amount=None, ip_address=None):
    case_id = transaction_case.pk
    # PostgreSQL darf FOR UPDATE nicht auf die nullable Seite eines OUTER JOIN
    # anwenden. Deshalb wird ausschließlich die Fallzeile gesperrt und die
    # benötigten Beziehungen anschließend in einer separaten Abfrage geladen.
    TransactionCase.objects.select_for_update().only("pk").get(pk=case_id)
    transaction_case = TransactionCase.objects.select_related(
        "business",
        "location",
        "wallet",
        "wallet__owner",
        "ledger_entry",
        "ledger_entry__performed_by",
        "opened_by",
    ).get(pk=case_id)
    membership = require_role(reviewer, transaction_case.business, MANAGER_ROLES)
    if not transaction_case.can_be_reviewed:
        raise ValidationError("Dieser Fall wurde bereits abgeschlossen.")
    if action not in {
        TransactionCase.Status.IN_REVIEW,
        TransactionCase.Status.APPROVED,
        TransactionCase.Status.REJECTED,
    }:
        raise ValidationError("Ungültige Entscheidung.")

    refund_entry = None
    approved = None
    if action == TransactionCase.Status.APPROVED:
        if membership.role not in OWNER_ROLES:
            raise PermissionDenied("Nur der Inhaber darf eine Erstattung genehmigen.")
        if transaction_case.ledger_entry.amount >= 0:
            raise ValidationError("Diese Transaktion kann nicht als Guthaben erstattet werden.")
        approved = normalize_amount(approved_amount)
        original_amount = abs(transaction_case.ledger_entry.amount)
        already_refunded = TransactionCase.objects.filter(
            ledger_entry=transaction_case.ledger_entry,
            status=TransactionCase.Status.APPROVED,
        ).exclude(pk=transaction_case.pk).aggregate(total=Sum("approved_amount"))["total"] or Decimal("0.00")
        remaining = original_amount - already_refunded
        if approved > remaining:
            raise ValidationError(f"Maximal noch {remaining:.2f} € erstattbar.")
        refund_entry = post_wallet_entry(
            wallet=transaction_case.wallet,
            location=transaction_case.location,
            entry_type=LedgerEntry.Type.REFUND,
            amount=approved,
            actor=reviewer,
            description=f"Erstattung zu Fall {transaction_case.case_number}",
            order_reference=transaction_case.ledger_entry.bill_number,
            idempotency_key=f"case-refund:{transaction_case.pk}",
            ip_address=ip_address,
        )

    transaction_case.status = action
    transaction_case.manager_note = manager_note.strip()
    transaction_case.approved_amount = approved
    transaction_case.refund_entry = refund_entry
    transaction_case.reviewed_by = reviewer
    transaction_case.reviewed_at = timezone.now()
    transaction_case.save(update_fields=[
        "status",
        "manager_note",
        "approved_amount",
        "refund_entry",
        "reviewed_by",
        "reviewed_at",
        "updated_at",
    ])

    recipients = [transaction_case.opened_by, transaction_case.wallet.owner, transaction_case.ledger_entry.performed_by]
    title = {
        TransactionCase.Status.IN_REVIEW: "Transaktionsfall wird geprüft",
        TransactionCase.Status.APPROVED: "Erstattung genehmigt",
        TransactionCase.Status.REJECTED: "Transaktionsfall abgeschlossen",
    }[action]
    body = f"{transaction_case.case_number} · {transaction_case.get_status_display()}."
    if approved:
        body += f" {approved:.2f} € wurden dem Mitgliedsguthaben gutgeschrieben."
    if manager_note:
        body += f" Hinweis: {manager_note.strip()}"
    create_notifications(
        users=recipients,
        business=transaction_case.business,
        location=transaction_case.location,
        title=title,
        body=body,
        data={
            "url": reverse("transaction_case_detail", args=[transaction_case.pk]),
            "transaction_case_id": str(transaction_case.pk),
        },
    )
    AuditEvent.objects.create(
        actor=reviewer,
        business=transaction_case.business,
        action=f"transaction_case.{action.lower()}",
        object_type="transaction_case",
        object_id=str(transaction_case.pk),
        ip_address=ip_address,
        details={
            "case_number": transaction_case.case_number,
            "approved_amount": str(approved) if approved else None,
            "refund_entry_id": str(refund_entry.pk) if refund_entry else None,
        },
    )
    return transaction_case
