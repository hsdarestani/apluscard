import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token

from cards.models import Business, LedgerEntry, Membership, Wallet
from cards.services import post_wallet_entry


class Command(BaseCommand):
    help = "Create the initial production business, users and customer wallet without overwriting existing passwords."

    def _required(self, name):
        value = os.getenv(name, "").strip()
        if not value:
            raise CommandError(f"Missing required environment variable: {name}")
        return value

    def handle(self, *args, **options):
        User = get_user_model()

        owner_username = self._required("INITIAL_OWNER_USERNAME")
        owner_password = self._required("INITIAL_OWNER_PASSWORD")
        staff_username = self._required("INITIAL_STAFF_USERNAME")
        staff_password = self._required("INITIAL_STAFF_PASSWORD")
        customer_username = self._required("INITIAL_CUSTOMER_USERNAME")
        customer_password = self._required("INITIAL_CUSTOMER_PASSWORD")

        business, _ = Business.objects.get_or_create(
            slug="shisha-bar",
            defaults={"name": "Shisha Bar", "currency": "EUR"},
        )

        owner, owner_created = User.objects.get_or_create(
            username=owner_username,
            defaults={"email": "owner@cards.smarbiz.sbs"},
        )
        if owner_created:
            owner.set_password(owner_password)
        owner.is_staff = True
        owner.is_superuser = True
        owner.save()
        Membership.objects.update_or_create(
            user=owner,
            business=business,
            defaults={"role": Membership.Role.OWNER, "is_active": True},
        )

        staff, staff_created = User.objects.get_or_create(
            username=staff_username,
            defaults={"email": "staff@cards.smarbiz.sbs"},
        )
        if staff_created:
            staff.set_password(staff_password)
            staff.save()
        Membership.objects.update_or_create(
            user=staff,
            business=business,
            defaults={"role": Membership.Role.STAFF, "is_active": True},
        )

        customer, customer_created = User.objects.get_or_create(
            username=customer_username,
            defaults={
                "email": "customer@cards.smarbiz.sbs",
                "first_name": "Max",
                "last_name": "Mustermann",
            },
        )
        if customer_created:
            customer.set_password(customer_password)
            customer.save()

        wallet, _ = Wallet.objects.get_or_create(
            business=business,
            owner=customer,
            defaults={
                "display_name": "Max Mustermann",
                "email": customer.email,
            },
        )

        if not wallet.ledger_entries.exists():
            post_wallet_entry(
                wallet=wallet,
                entry_type=LedgerEntry.Type.TOPUP,
                amount="200.00",
                actor=owner,
                description="Initiale Aufladung",
                idempotency_key="production-bootstrap-topup",
            )
            post_wallet_entry(
                wallet=wallet,
                entry_type=LedgerEntry.Type.BONUS,
                amount="20.00",
                actor=owner,
                description="10% Willkommensbonus",
                idempotency_key="production-bootstrap-bonus",
            )

        for user in (owner, staff, customer):
            Token.objects.get_or_create(user=user)

        self.stdout.write(self.style.SUCCESS("Production bootstrap completed."))
        self.stdout.write(f"Business: {business.name}")
        self.stdout.write(f"Owner: {owner.username}")
        self.stdout.write(f"Staff: {staff.username}")
        self.stdout.write(f"Customer: {customer.username}")
        self.stdout.write(f"Customer balance: {wallet.balance} EUR")
