from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework.authtoken.models import Token

from .compliance_models import TestWalletMarker
from .experience_models import TransactionCase
from .legal_models import AccountDeletionRequest, LegalAcceptance, PrivacyPreference
from .models import (
    AppNotification,
    AuditEvent,
    Business,
    LedgerEntry,
    Membership,
    Offer,
    PaymentRequest,
    PushDevice,
    ReviewStatus,
    Wallet,
)
from .push_models import PushDelivery


DEMO_BUSINESS_SLUG = "demo-lounge"
DEMO_USERNAMES = {"owner", "staff", "customer"}


def _candidate_users():
    User = get_user_model()
    return User.objects.filter(
        Q(email__iendswith="@example.com")
        | Q(username__in=DEMO_USERNAMES, business_memberships__business__slug=DEMO_BUSINESS_SLUG)
    ).distinct()


def _test_wallets():
    candidate_users = _candidate_users()
    return Wallet.objects.filter(
        Q(test_data_marker__isnull=False)
        | Q(business__slug=DEMO_BUSINESS_SLUG)
        | Q(owner__in=candidate_users)
    ).distinct()


def _test_payment_requests():
    return PaymentRequest.objects.filter(wallet__in=_test_wallets())


def _test_ledger_entries():
    return LedgerEntry.objects.filter(wallet__in=_test_wallets())


def _test_notifications():
    candidate_users = _candidate_users()
    payment_ids = [str(value) for value in _test_payment_requests().values_list("pk", flat=True)]
    query = Q(recipient__in=candidate_users) | Q(business__slug=DEMO_BUSINESS_SLUG)
    if payment_ids:
        query |= Q(data__payment_request_id__in=payment_ids)
    query |= Q(data__production_smoke_test=True)
    return AppNotification.objects.filter(query).distinct()


def _blocked_candidate_users():
    """Users that look like test users but have protected references outside test scope."""
    users = _candidate_users()
    test_wallets = _test_wallets()
    demo_businesses = Business.objects.filter(slug=DEMO_BUSINESS_SLUG)
    blocked_ids = set(
        PaymentRequest.objects.filter(created_by__in=users)
        .exclude(wallet__in=test_wallets)
        .values_list("created_by_id", flat=True)
    )
    blocked_ids.update(
        LedgerEntry.objects.filter(performed_by__in=users)
        .exclude(wallet__in=test_wallets)
        .values_list("performed_by_id", flat=True)
    )
    blocked_ids.update(
        Offer.objects.filter(created_by__in=users)
        .exclude(business__in=demo_businesses)
        .values_list("created_by_id", flat=True)
    )
    blocked_ids.update(
        TransactionCase.objects.filter(opened_by__in=users)
        .exclude(wallet__in=test_wallets)
        .values_list("opened_by_id", flat=True)
    )
    return users.filter(pk__in=blocked_ids)


def build_test_data_preview():
    candidate_users = _candidate_users()
    blocked_users = _blocked_candidate_users()
    deletable_users = candidate_users.exclude(pk__in=blocked_users.values("pk"))
    test_wallets = _test_wallets()
    payments = _test_payment_requests()
    ledger = _test_ledger_entries()
    notifications = _test_notifications()
    demo_businesses = Business.objects.filter(slug=DEMO_BUSINESS_SLUG)

    counts = OrderedDict(
        [
            ("Test-Markierungen", TestWalletMarker.objects.filter(wallet__in=test_wallets).count()),
            ("Test-Benutzer löschbar", deletable_users.count()),
            ("Test-Benutzer blockiert", blocked_users.count()),
            ("Test-Wallets", test_wallets.count()),
            ("Zahlungsanfragen", payments.count()),
            ("Ledger-Buchungen", ledger.count()),
            ("Transaktionsfälle", TransactionCase.objects.filter(wallet__in=test_wallets).count()),
            ("Bewertungsstatus", ReviewStatus.objects.filter(wallet__in=test_wallets).count()),
            ("App-Mitteilungen", notifications.count()),
            ("Push-Zustellungen", PushDelivery.objects.filter(notification__in=notifications).count()),
            ("Push-Geräte reiner Test-Benutzer", PushDevice.objects.filter(user__in=deletable_users).count()),
            ("Mitgliedschaften reiner Test-Benutzer", Membership.objects.filter(user__in=deletable_users).count()),
            ("Datenschutzpräferenzen", PrivacyPreference.objects.filter(user__in=deletable_users).count()),
            ("Rechtliche Bestätigungen", LegalAcceptance.objects.filter(user__in=deletable_users).count()),
            ("Löschanträge", AccountDeletionRequest.objects.filter(Q(user__in=deletable_users) | Q(wallet__in=test_wallets)).count()),
            ("Demo-Betriebe", demo_businesses.count()),
        ]
    )
    return {
        "counts": counts,
        "candidate_user_count": candidate_users.count(),
        "blocked_user_count": blocked_users.count(),
        "deletable_user_count": deletable_users.count(),
        "total_records": sum(counts.values()),
    }


@transaction.atomic
def purge_test_data():
    """Delete only explicitly/structurally identified test data.

    Real users who merely interacted with an explicitly marked smoke-test wallet
    are retained. Candidate demo users are deleted only when they have no
    protected references outside the test scope.
    """
    candidate_users = _candidate_users()
    blocked_users = _blocked_candidate_users()
    deletable_users = candidate_users.exclude(pk__in=blocked_users.values("pk"))
    test_wallets = _test_wallets()
    payments = _test_payment_requests()
    ledger = _test_ledger_entries()
    notifications = _test_notifications()
    demo_businesses = Business.objects.filter(slug=DEMO_BUSINESS_SLUG)

    # Delete queue/notification history first so no stale test push survives.
    PushDelivery.objects.filter(notification__in=notifications).delete()
    notifications.delete()

    # Remove wallet-dependent records in PROTECT-safe order.
    TransactionCase.objects.filter(wallet__in=test_wallets).delete()
    AccountDeletionRequest.objects.filter(Q(user__in=deletable_users) | Q(wallet__in=test_wallets)).delete()
    ReviewStatus.objects.filter(wallet__in=test_wallets).delete()
    payments.delete()
    ledger.delete()
    TestWalletMarker.objects.filter(wallet__in=test_wallets).delete()

    # Remove purely test-user data. Protected references outside test scope were
    # detected above and keep those users out of this queryset.
    Token.objects.filter(user__in=deletable_users).delete()
    PushDevice.objects.filter(user__in=deletable_users).delete()
    PrivacyPreference.objects.filter(user__in=deletable_users).delete()
    LegalAcceptance.objects.filter(user__in=deletable_users).delete()
    Membership.objects.filter(user__in=deletable_users).delete()

    # Audit rows from demo business are test records; audit rows on real business
    # are retained even when their actor was a deletable test account.
    AuditEvent.objects.filter(business__in=demo_businesses).delete()
    Offer.objects.filter(business__in=demo_businesses).delete()

    # Wallets can now be removed. A marked smoke wallet may belong to a real
    # owner; only the wallet is deleted, never that owner account.
    test_wallets.delete()

    # Django cascades profiles/social accounts for the remaining pure test users.
    deletable_users.delete()

    # Demo business can be removed only after protected financial/legal rows are gone.
    LegalAcceptance.objects.filter(business__in=demo_businesses).delete()
    AccountDeletionRequest.objects.filter(business__in=demo_businesses).delete()
    demo_businesses.delete()

    return build_test_data_preview()
