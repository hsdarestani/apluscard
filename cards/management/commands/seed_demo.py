from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from cards.models import Business, LedgerEntry, Membership, Wallet
from cards.services import post_wallet_entry


class Command(BaseCommand):
    help = "Create a demo business and demo users."

    def handle(self, *args, **options):
        User = get_user_model()
        business, _ = Business.objects.get_or_create(name="Demo Lounge", slug="demo-lounge", defaults={"currency": "EUR"})
        owner, _ = User.objects.get_or_create(username="owner", defaults={"email": "owner@example.com"})
        owner.set_password("ChangeMe123!")
        owner.is_staff = True
        owner.is_superuser = True
        owner.save()
        Membership.objects.update_or_create(user=owner, business=business, defaults={"role": Membership.Role.OWNER})
        staff, _ = User.objects.get_or_create(username="staff", defaults={"email": "staff@example.com"})
        staff.set_password("ChangeMe123!")
        staff.save()
        Membership.objects.update_or_create(user=staff, business=business, defaults={"role": Membership.Role.STAFF})
        customer, _ = User.objects.get_or_create(username="customer", defaults={"email": "customer@example.com", "first_name": "Max"})
        customer.set_password("ChangeMe123!")
        customer.save()
        wallet, _ = Wallet.objects.get_or_create(business=business, owner=customer, defaults={"display_name": "Max Mustermann", "email": customer.email})
        if wallet.balance == 0:
            post_wallet_entry(wallet=wallet, entry_type=LedgerEntry.Type.TOPUP, amount="200.00", actor=owner, description="Demo-Aufladung")
        for user in (owner, staff, customer):
            Token.objects.get_or_create(user=user)
        self.stdout.write(self.style.SUCCESS("Demo created:"))
        self.stdout.write("owner / ChangeMe123!")
        self.stdout.write("staff / ChangeMe123!")
        self.stdout.write("customer / ChangeMe123!")
        self.stdout.write(f"Customer QR token: {wallet.qr_token}")
