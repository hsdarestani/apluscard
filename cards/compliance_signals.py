from django.conf import settings
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .experience_models import TransactionCase
from .models import AuditEvent, LedgerEntry, PaymentRequest


IMMUTABLE_FINANCIAL_MODELS = (
    LedgerEntry,
    PaymentRequest,
    TransactionCase,
    AuditEvent,
)


def _protect_financial_record(instance):
    if settings.ALLOW_TEST_DATA_PURGE:
        return
    raise ProtectedError(
        "Produktive Finanz- und Auditdaten sind unveränderlich. Bitte eine Gegenbuchung oder einen Prüffall verwenden.",
        [instance],
    )


@receiver(pre_delete, sender=LedgerEntry, dispatch_uid="protect_ledger_entry_delete")
def protect_ledger_entry_delete(sender, instance, **kwargs):
    _protect_financial_record(instance)


@receiver(pre_delete, sender=PaymentRequest, dispatch_uid="protect_payment_request_delete")
def protect_payment_request_delete(sender, instance, **kwargs):
    _protect_financial_record(instance)


@receiver(pre_delete, sender=TransactionCase, dispatch_uid="protect_transaction_case_delete")
def protect_transaction_case_delete(sender, instance, **kwargs):
    _protect_financial_record(instance)


@receiver(pre_delete, sender=AuditEvent, dispatch_uid="protect_audit_event_delete")
def protect_audit_event_delete(sender, instance, **kwargs):
    _protect_financial_record(instance)
