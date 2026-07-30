import logging
import secrets
import uuid

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from .apple_credentials import revoke_apple_credentials
from .legal_models import AccountDeletionRequest, LegalAcceptance, PrivacyPreference
from .models import AppNotification, MemberProfile, PushDevice, Wallet

logger = logging.getLogger(__name__)
DELETION_COMPLETION_DAYS = 7


def _send_deletion_email(*, to_email, subject, body):
    email = str(to_email or "").strip()
    if not email:
        return False
    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
        reply_to=[settings.EMAIL_REPLY_TO],
    )
    sent = message.send(fail_silently=False)
    if sent != 1:
        raise RuntimeError("Der Mailserver hat die Nachricht zur Kontolöschung nicht angenommen.")
    return True


def send_deletion_received_email(deletion_request):
    """Acknowledge a deletion request and state the processing timeframe."""
    return _send_deletion_email(
        to_email=deletion_request.email,
        subject=f"{settings.APP_NAME} – Antrag auf Kontolöschung eingegangen",
        body=(
            "Hallo,\n\n"
            "dein Antrag auf Löschung des Kontos und der nicht mehr benötigten personenbezogenen Daten ist eingegangen.\n\n"
            f"Referenznummer: {deletion_request.reference_number}\n"
            f"Bearbeitungszeit: spätestens innerhalb von {DELETION_COMPLETION_DAYS} Kalendertagen.\n\n"
            "Offene Guthaben- oder Zahlungsvorgänge und gesetzliche Aufbewahrungspflichten werden vor Abschluss geprüft. "
            "Nicht mehr benötigte Konto-, Kontakt-, Profil- und Push-Daten werden gelöscht oder anonymisiert. "
            "Nach Abschluss erhältst du eine Bestätigung per E-Mail.\n\n"
            f"{settings.APP_NAME}\n{settings.APP_PUBLISHER}"
        ),
    )


def send_deletion_completed_email(*, to_email, reference_number):
    """Confirm that the account deletion workflow has completed."""
    return _send_deletion_email(
        to_email=to_email,
        subject=f"{settings.APP_NAME} – Kontolöschung abgeschlossen",
        body=(
            "Hallo,\n\n"
            "die Löschung deines Kontos und der nicht mehr benötigten personenbezogenen Daten wurde abgeschlossen.\n\n"
            f"Referenznummer: {reference_number}\n\n"
            "Direkte Konto-, Kontakt-, Profil-, Push- und Anmeldedaten wurden gelöscht oder anonymisiert. "
            "Gesetzlich aufzubewahrende Transaktions-, Beleg-, Steuer- und Prüfunterlagen können bis zum Ablauf "
            "der jeweiligen Frist in anonymisierter oder pseudonymisierter Form gespeichert bleiben.\n\n"
            f"{settings.APP_NAME}\n{settings.APP_PUBLISHER}"
        ),
    )


def _resolve_account(deletion_request):
    user = deletion_request.user
    wallet = deletion_request.wallet

    if wallet is None and deletion_request.member_number:
        wallet_query = Wallet.objects.filter(
            business=deletion_request.business,
            member_number=deletion_request.member_number,
        )
        if deletion_request.email:
            wallet_query = wallet_query.filter(Q(email__iexact=deletion_request.email) | Q(owner__email__iexact=deletion_request.email))
        wallet = wallet_query.select_related("owner").first()

    if user is None and wallet is not None:
        user = wallet.owner

    if user is None and deletion_request.email:
        user = get_user_model().objects.filter(email__iexact=deletion_request.email).first()

    return user, wallet


def _anonymize_wallet(wallet):
    wallet.owner = None
    wallet.display_name = f"Gelöschtes Mitglied {wallet.member_number[-4:]}"
    wallet.phone = ""
    wallet.email = ""
    wallet.qr_token = uuid.uuid4()
    wallet.status = Wallet.Status.CLOSED
    wallet.save(
        update_fields=[
            "owner",
            "display_name",
            "phone",
            "email",
            "qr_token",
            "status",
            "updated_at",
        ]
    )


def _anonymize_protected_user(user):
    """Remove direct identifiers when legal records protect the User row from deletion."""
    SocialAccount.objects.filter(user=user).delete()
    PushDevice.objects.filter(user=user).delete()
    AppNotification.objects.filter(recipient=user).delete()
    PrivacyPreference.objects.filter(user=user).delete()
    MemberProfile.objects.filter(user=user).delete()
    LegalAcceptance.objects.filter(user=user).update(user=None)
    AccountDeletionRequest.objects.filter(user=user).update(user=None)
    user.business_memberships.all().delete()
    user.groups.clear()
    user.user_permissions.clear()

    user.username = f"deleted_{user.pk}_{secrets.token_hex(8)}"
    user.email = ""
    user.first_name = ""
    user.last_name = ""
    user.is_active = False
    user.is_staff = False
    user.is_superuser = False
    user.set_unusable_password()
    user.save(
        update_fields=[
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "password",
        ]
    )


@transaction.atomic
def complete_account_deletion(deletion_request):
    """Revoke Apple access and erase/anonymize the account behind an approved request."""
    # Lock only the request row first. PostgreSQL rejects FOR UPDATE when a
    # select_related() outer join reaches nullable user/wallet relations.
    locked_request = AccountDeletionRequest.objects.select_for_update().get(pk=deletion_request.pk)
    deletion_request = AccountDeletionRequest.objects.select_related(
        "business",
        "user",
        "wallet__owner",
    ).get(pk=locked_request.pk)

    if deletion_request.status == AccountDeletionRequest.Status.COMPLETED:
        return {"status": "already_completed", "reference": deletion_request.reference_number}

    original_email = deletion_request.email
    reference_number = deletion_request.reference_number
    user, primary_wallet = _resolve_account(deletion_request)
    apple_revocation = revoke_apple_credentials(user)

    wallets = Wallet.objects.none()
    if user is not None:
        wallets = Wallet.objects.filter(owner=user)
    if primary_wallet is not None:
        wallets = Wallet.objects.filter(Q(pk__in=wallets.values("pk")) | Q(pk=primary_wallet.pk))

    for wallet in wallets.select_for_update():
        _anonymize_wallet(wallet)

    deletion_mode = "no_account_match"
    if user is not None:
        user_id = user.pk
        LegalAcceptance.objects.filter(user=user).update(user=None)
        AccountDeletionRequest.objects.filter(user=user).update(user=None)
        try:
            # Keep a savepoint around Collector.delete(); a protected legal row
            # must not poison the surrounding deletion transaction.
            with transaction.atomic():
                user.delete()
            deletion_mode = "deleted"
        except ProtectedError:
            logger.info("Protected records require user anonymization for user_id=%s", user_id)
            user = get_user_model().objects.get(pk=user_id)
            _anonymize_protected_user(user)
            deletion_mode = "anonymized_for_legal_retention"

    deletion_request.user = None
    deletion_request.email = f"deleted+{reference_number.lower()}@example.invalid"
    deletion_request.member_number = ""
    deletion_request.reason = ""
    deletion_request.requested_ip = None
    deletion_request.requested_user_agent = ""
    deletion_request.status = AccountDeletionRequest.Status.COMPLETED
    deletion_request.completed_at = timezone.now()
    deletion_request.internal_note = (
        f"Account deletion: {deletion_mode}; Apple credential revocation: {apple_revocation}. "
        "Direct identifiers removed; legally retained transaction records remain anonymized/pseudonymized."
    )
    deletion_request.save(
        update_fields=[
            "user",
            "email",
            "member_number",
            "reason",
            "requested_ip",
            "requested_user_agent",
            "status",
            "completed_at",
            "internal_note",
        ]
    )

    def notify_completion():
        try:
            send_deletion_completed_email(to_email=original_email, reference_number=reference_number)
        except Exception:
            logger.exception("Deletion completion email failed for reference=%s", reference_number)

    transaction.on_commit(notify_completion)
    return {
        "status": deletion_mode,
        "apple_revocation": apple_revocation,
        "reference": reference_number,
    }
