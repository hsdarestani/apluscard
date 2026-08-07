import time
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from cards.compliance_models import TestWalletMarker
from cards.management.commands.run_push_worker import enqueue_recent_notifications
from cards.models import AppNotification, Location, Membership, PaymentRequest, PushDevice, Wallet
from cards.push_models import PushDelivery
from cards.services import create_payment_request


class Command(BaseCommand):
    help = "Prüft den echten Payment→Notification→Queue→Worker→Push-Pfad mit einem markierten internen Testkonto."

    def _find_or_create_test_wallet(self):
        memberships = (
            Membership.objects.filter(
                is_active=True,
                role__in=[Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.STAFF],
                user__push_devices__is_active=True,
                user__push_devices__platform__in=[PushDevice.Platform.ANDROID, PushDevice.Platform.IOS],
            )
            .select_related("user", "business")
            .distinct()
            .order_by("role", "created_at")
        )

        for membership in memberships:
            location = Location.objects.filter(business=membership.business, is_active=True).order_by("created_at").first()
            if location is None:
                continue

            wallet = Wallet.objects.filter(business=membership.business, owner=membership.user).first()
            if wallet is not None:
                if not TestWalletMarker.objects.filter(wallet=wallet).exists():
                    # Never convert or mutate a real wallet just to run a smoke test.
                    continue
            else:
                wallet = Wallet.objects.create(
                    business=membership.business,
                    owner=membership.user,
                    display_name="SAMS Push Smoke Test",
                    email=membership.user.email or "",
                    balance=Decimal("1.00"),
                )
                TestWalletMarker.objects.create(
                    wallet=wallet,
                    reason="Automatisches Production Transaction-Push-Smoke-Testkonto",
                    marked_by=membership.user,
                )

            if wallet.status != Wallet.Status.ACTIVE:
                wallet.status = Wallet.Status.ACTIVE
                wallet.save(update_fields=["status", "updated_at"])
            if wallet.balance < Decimal("0.10"):
                # This wallet is explicitly marked as disposable test data. Resetting
                # only its balance keeps the smoke test isolated from real accounts.
                wallet.balance = Decimal("1.00")
                wallet.save(update_fields=["balance", "updated_at"])

            return membership, wallet, location

        raise CommandError(
            "Kein geeignetes internes Push-Gerät gefunden. Ein reales Kundenkonto wird für den Smoke-Test niemals verwendet."
        )

    def handle(self, *args, **options):
        membership, wallet, location = self._find_or_create_test_wallet()
        before_balance = wallet.balance

        payment = create_payment_request(
            wallet=wallet,
            location=location,
            actor=membership.user,
            amount=Decimal("0.01"),
            tip_amount=Decimal("0.00"),
            description="Automatischer Transaction-Push-Smoke-Test",
            order_reference=f"PUSH-SMOKE-{int(time.time())}",
            force_immediate=True,
        )
        if payment.status != PaymentRequest.Status.CONFIRMED:
            raise CommandError(f"Testzahlung wurde nicht bestätigt: {payment.status}")

        notification = (
            AppNotification.objects.filter(
                recipient=membership.user,
                kind=AppNotification.Kind.PAYMENT,
                data__payment_request_id=str(payment.pk),
                title="A+ Pay Zahlung abgeschlossen",
            )
            .order_by("-created_at")
            .first()
        )
        if notification is None:
            raise CommandError("Payment wurde bestätigt, aber die Payment-Mitteilung fehlt.")

        # Defensive backfill in case queue creation was delayed for any reason.
        enqueue_recent_notifications()
        delivery = PushDelivery.objects.filter(notification=notification).first()
        if delivery is None:
            raise CommandError("Payment-Mitteilung wurde erstellt, aber nicht in die Push-Queue gestellt.")

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            delivery.refresh_from_db()
            if delivery.status == PushDelivery.Status.SENT:
                if delivery.sent_count < 1:
                    raise CommandError("PushDelivery ist SENT, aber sent_count ist 0.")
                wallet.refresh_from_db(fields=["balance"])
                self.stdout.write(
                    self.style.SUCCESS(
                        "Transaction Push Smoke OK · "
                        f"Payment={payment.pk} · Notification={notification.pk} · "
                        f"Delivery={delivery.pk} · sent={delivery.sent_count} · "
                        f"Balance {before_balance:.2f}→{wallet.balance:.2f} €"
                    )
                )
                return
            if delivery.status in {PushDelivery.Status.FAILED, PushDelivery.Status.SKIPPED}:
                raise CommandError(
                    f"PushDelivery {delivery.status}: {delivery.last_error or 'ohne Fehlerdetail'}"
                )
            if delivery.status == PushDelivery.Status.RETRY and delivery.last_error:
                raise CommandError(f"PushDelivery RETRY: {delivery.last_error}")
            time.sleep(1)

        delivery.refresh_from_db()
        raise CommandError(
            "Push-Worker hat die Transaktionsmitteilung nicht rechtzeitig abgeschlossen: "
            f"status={delivery.status}, attempts={delivery.attempts}, error={delivery.last_error!r}"
        )
