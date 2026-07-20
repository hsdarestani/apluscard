import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Rotate the production owner and staff passwords from environment variables."

    def _required(self, name):
        value = os.getenv(name, "")
        if not value:
            raise CommandError(f"Missing required environment variable: {name}")
        return value

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        owner_username = os.getenv("OWNER_APP_USERNAME", "owner").strip() or "owner"
        staff_username = os.getenv("STAFF_APP_USERNAME", "staff").strip() or "staff"
        owner_password = self._required("OWNER_APP_PASSWORD")
        staff_password = self._required("STAFF_APP_PASSWORD")

        try:
            owner = User.objects.get(username=owner_username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Owner account not found: {owner_username}") from exc
        try:
            staff = User.objects.get(username=staff_username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Staff account not found: {staff_username}") from exc

        owner.set_password(owner_password)
        owner.save(update_fields=["password"])
        staff.set_password(staff_password)
        staff.save(update_fields=["password"])

        self.stdout.write(self.style.SUCCESS("Owner and staff passwords were rotated successfully."))
