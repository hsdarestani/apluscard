from collections import Counter

import dj_database_url
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, connections, transaction
from django.db.models import Q
from rest_framework.authtoken.models import Token

from cards.compliance_models import TestWalletMarker
from cards.experience_models import LocationVisual, MemberNumberSequence, TransactionCase
from cards.legal_models import AccountDeletionRequest, LegalAcceptance, LegalConfiguration, PrivacyPreference
from cards.models import (
    AppNotification,
    AuditEvent,
    Business,
    BusinessSettings,
    LedgerEntry,
    Location,
    MemberProfile,
    Membership,
    Offer,
    PaymentRequest,
    PushDevice,
    ReviewStatus,
    Wallet,
)


class Command(BaseCommand):
    help = (
        "Vereinigt fehlende Datensätze aus einer eingefrorenen Legacy-PostgreSQL-Datenbank "
        "mit der kanonischen Production-Datenbank. Bestehende aktuelle Datensätze gewinnen immer."
    )

    def add_arguments(self, parser):
        parser.add_argument("--legacy-db-name", required=True)

    def handle(self, *args, **options):
        legacy_db_name = options["legacy_db_name"].strip()
        if not legacy_db_name or legacy_db_name == connection.settings_dict.get("NAME"):
            raise CommandError("Legacy-Datenbank muss eine separate temporäre Datenbank sein.")
        if connection.vendor != "postgresql":
            raise CommandError("Reconciliation ist ausschließlich für PostgreSQL freigegeben.")

        legacy_config = dict(settings.DATABASES["default"])
        legacy_config["NAME"] = legacy_db_name
        legacy_config["CONN_MAX_AGE"] = 0
        connections.databases["legacy"] = legacy_config
        try:
            with connections["legacy"].cursor() as cursor:
                cursor.execute("SELECT current_database()")
                resolved = cursor.fetchone()[0]
            if resolved != legacy_db_name:
                raise CommandError(f"Falsche Legacy-Datenbank geöffnet: {resolved}")

            with transaction.atomic(using="default"):
                stats = self._reconcile()
                self._reset_sequences()
                self._validate(stats)
        finally:
            connections["legacy"].close()

        self.stdout.write(self.style.SUCCESS("Legacy-Reconciliation vollständig und konsistent abgeschlossen."))
        for key in sorted(stats):
            self.stdout.write(f"{key}={stats[key]}")

    @staticmethod
    def _fields(model):
        return [field for field in model._meta.concrete_fields]

    def _legacy_rows(self, model):
        names = [field.attname for field in self._fields(model)]
        return model.objects.using("legacy").values(*names).iterator(chunk_size=500)

    def _raw_insert(self, model, row, *, preserve_pk=True, transforms=None):
        data = dict(row)
        if transforms:
            for key, value in transforms.items():
                data[key] = value
        if not preserve_pk:
            data[model._meta.pk.attname] = None
        obj = model()
        for field in self._fields(model):
            setattr(obj, field.attname, data.get(field.attname))
        obj.save_base(raw=True, force_insert=True, using="default")
        return obj.pk

    @staticmethod
    def _one_candidate(queryset, label):
        ids = list(queryset.values_list("pk", flat=True).distinct()[:3])
        if len(ids) > 1:
            raise CommandError(f"Mehrdeutige Zuordnung für {label}; automatischer Merge abgebrochen.")
        return ids[0] if ids else None

    def _insert_leaf(self, model, row, *, transforms=None):
        old_pk = row[model._meta.pk.attname]
        preserve = not model.objects.filter(pk=old_pk).exists()
        return self._raw_insert(model, row, preserve_pk=preserve, transforms=transforms)

    def _reconcile(self):
        stats = Counter()
        User = get_user_model()

        user_map = {}
        for row in self._legacy_rows(User):
            old_id = row["id"]
            existing = User.objects.filter(pk=old_id).first()
            if existing:
                user_map[old_id] = existing.pk
                stats["users_current_wins"] += 1
                continue
            identity_q = Q(username=row["username"])
            if row.get("email"):
                identity_q |= Q(email__iexact=row["email"])
            identity = self._one_candidate(User.objects.filter(identity_q), f"Legacy-User {old_id}")
            if identity is not None:
                raise CommandError(
                    f"Legacy-User {old_id} kollidiert mit einem anderen aktuellen User-PK; Mapping muss manuell geprüft werden."
                )
            self._raw_insert(User, row, preserve_pk=True)
            user_map[old_id] = old_id
            stats["users_inserted"] += 1

        group_map = {}
        for row in self._legacy_rows(Group):
            old_id = row["id"]
            target = Group.objects.filter(pk=old_id).first() or Group.objects.filter(name=row["name"]).first()
            if target:
                group_map[old_id] = target.pk
                continue
            self._raw_insert(Group, row, preserve_pk=True)
            group_map[old_id] = old_id
            stats["groups_inserted"] += 1

        # Preserve legacy auth memberships for imported users without overriding current permissions.
        legacy_user_groups = User.groups.through.objects.using("legacy").values("user_id", "group_id")
        for row in legacy_user_groups.iterator(chunk_size=500):
            mapped_user = user_map.get(row["user_id"])
            mapped_group = group_map.get(row["group_id"])
            if mapped_user and mapped_group:
                User.groups.through.objects.get_or_create(user_id=mapped_user, group_id=mapped_group)

        legacy_user_permissions = User.user_permissions.through.objects.using("legacy").values("user_id", "permission_id")
        current_permission_ids = set(Permission.objects.values_list("pk", flat=True))
        for row in legacy_user_permissions.iterator(chunk_size=500):
            mapped_user = user_map.get(row["user_id"])
            permission_id = row["permission_id"]
            if mapped_user and permission_id in current_permission_ids:
                User.user_permissions.through.objects.get_or_create(user_id=mapped_user, permission_id=permission_id)

        business_map = {}
        for row in self._legacy_rows(Business):
            old_id = row["id"]
            target = Business.objects.filter(pk=old_id).first() or Business.objects.filter(slug=row["slug"]).first()
            if target:
                business_map[old_id] = target.pk
                continue
            self._raw_insert(Business, row, preserve_pk=True)
            business_map[old_id] = old_id
            stats["businesses_inserted"] += 1

        location_map = {}
        for row in self._legacy_rows(Location):
            old_id = row["id"]
            mapped_business = business_map[row["business_id"]]
            candidate = self._one_candidate(
                Location.objects.filter(Q(pk=old_id) | Q(business_id=mapped_business, slug=row["slug"])),
                f"Legacy-Location {old_id}",
            )
            if candidate:
                location_map[old_id] = candidate
                continue
            self._raw_insert(Location, row, preserve_pk=True, transforms={"business_id": mapped_business})
            location_map[old_id] = old_id
            stats["locations_inserted"] += 1

        # Singleton/configuration tables: current configuration always wins.
        for row in self._legacy_rows(BusinessSettings):
            mapped_business = business_map[row["business_id"]]
            if not BusinessSettings.objects.filter(business_id=mapped_business).exists():
                self._insert_leaf(BusinessSettings, row, transforms={"business_id": mapped_business})
                stats["business_settings_inserted"] += 1

        for row in self._legacy_rows(LegalConfiguration):
            mapped_business = business_map[row["business_id"]]
            if not LegalConfiguration.objects.filter(business_id=mapped_business).exists():
                self._insert_leaf(LegalConfiguration, row, transforms={"business_id": mapped_business})
                stats["legal_configurations_inserted"] += 1

        for row in self._legacy_rows(LocationVisual):
            mapped_location = location_map[row["location_id"]]
            if not LocationVisual.objects.filter(location_id=mapped_location).exists():
                self._insert_leaf(LocationVisual, row, transforms={"location_id": mapped_location})
                stats["location_visuals_inserted"] += 1

        # The sequence's larger value wins so a historical member number can never be reused.
        for row in self._legacy_rows(MemberNumberSequence):
            current = MemberNumberSequence.objects.filter(pk=row["id"]).first()
            if current:
                if current.next_number < row["next_number"]:
                    MemberNumberSequence.objects.filter(pk=current.pk).update(next_number=row["next_number"])
                    stats["member_sequence_advanced"] += 1
            else:
                self._raw_insert(MemberNumberSequence, row, preserve_pk=True)
                stats["member_sequence_inserted"] += 1

        wallet_map = {}
        for row in self._legacy_rows(Wallet):
            old_id = row["id"]
            mapped_business = business_map[row["business_id"]]
            mapped_owner = user_map.get(row["owner_id"]) if row["owner_id"] is not None else None
            q = Q(pk=old_id) | Q(member_number=row["member_number"]) | Q(qr_token=row["qr_token"])
            if mapped_owner is not None:
                q |= Q(business_id=mapped_business, owner_id=mapped_owner)
            candidate = self._one_candidate(Wallet.objects.filter(q), f"Legacy-Wallet {old_id}")
            if candidate:
                wallet_map[old_id] = candidate
                if candidate != old_id:
                    stats["wallets_mapped_to_existing_identity"] += 1
                else:
                    stats["wallets_current_wins"] += 1
                continue
            self._raw_insert(
                Wallet,
                row,
                preserve_pk=True,
                transforms={"business_id": mapped_business, "owner_id": mapped_owner},
            )
            wallet_map[old_id] = old_id
            stats["wallets_inserted"] += 1

        for row in self._legacy_rows(MemberProfile):
            mapped_user = user_map[row["user_id"]]
            if not MemberProfile.objects.filter(user_id=mapped_user).exists():
                self._insert_leaf(MemberProfile, row, transforms={"user_id": mapped_user})
                stats["member_profiles_inserted"] += 1

        for row in self._legacy_rows(Membership):
            mapped_user = user_map[row["user_id"]]
            mapped_business = business_map[row["business_id"]]
            if not Membership.objects.filter(user_id=mapped_user, business_id=mapped_business).exists():
                self._insert_leaf(
                    Membership,
                    row,
                    transforms={"user_id": mapped_user, "business_id": mapped_business},
                )
                stats["memberships_inserted"] += 1

        for row in self._legacy_rows(PrivacyPreference):
            mapped_user = user_map[row["user_id"]]
            mapped_business = business_map[row["business_id"]]
            if not PrivacyPreference.objects.filter(user_id=mapped_user, business_id=mapped_business).exists():
                self._insert_leaf(
                    PrivacyPreference,
                    row,
                    transforms={"user_id": mapped_user, "business_id": mapped_business},
                )
                stats["privacy_preferences_inserted"] += 1

        for row in self._legacy_rows(EmailAddress):
            mapped_user = user_map[row["user_id"]]
            existing = EmailAddress.objects.filter(email__iexact=row["email"]).first()
            if existing:
                if existing.user_id != mapped_user:
                    raise CommandError("Legacy-E-Mail-Adresse gehört in Current zu einem anderen Benutzer.")
                continue
            self._insert_leaf(EmailAddress, row, transforms={"user_id": mapped_user})
            stats["email_addresses_inserted"] += 1

        for row in self._legacy_rows(SocialAccount):
            mapped_user = user_map[row["user_id"]]
            existing = SocialAccount.objects.filter(provider=row["provider"], uid=row["uid"]).first()
            if existing:
                if existing.user_id != mapped_user:
                    raise CommandError("Legacy-Social-Login gehört in Current zu einem anderen Benutzer.")
                continue
            self._insert_leaf(SocialAccount, row, transforms={"user_id": mapped_user})
            stats["social_accounts_inserted"] += 1

        for row in self._legacy_rows(Token):
            mapped_user = user_map[row["user_id"]]
            if Token.objects.filter(Q(pk=row["key"]) | Q(user_id=mapped_user)).exists():
                continue
            self._raw_insert(Token, row, preserve_pk=True, transforms={"user_id": mapped_user})
            stats["api_tokens_inserted"] += 1

        for row in self._legacy_rows(LegalAcceptance):
            mapped_user = user_map.get(row["user_id"]) if row["user_id"] is not None else None
            mapped_business = business_map[row["business_id"]]
            if mapped_user is not None:
                duplicate = LegalAcceptance.objects.filter(
                    user_id=mapped_user,
                    business_id=mapped_business,
                    document_type=row["document_type"],
                    version=row["version"],
                ).exists()
            else:
                duplicate = LegalAcceptance.objects.filter(
                    user__isnull=True,
                    business_id=mapped_business,
                    document_type=row["document_type"],
                    version=row["version"],
                    email_hash=row["email_hash"],
                    member_number=row["member_number"],
                    accepted_at=row["accepted_at"],
                ).exists()
            if duplicate:
                continue
            self._insert_leaf(
                LegalAcceptance,
                row,
                transforms={"user_id": mapped_user, "business_id": mapped_business},
            )
            stats["legal_acceptances_inserted"] += 1

        payment_map = {}
        inserted_payment_ids = set()
        legacy_payment_links = {}
        for row in self._legacy_rows(PaymentRequest):
            old_id = row["id"]
            if PaymentRequest.objects.filter(pk=old_id).exists():
                payment_map[old_id] = old_id
                stats["payments_current_wins"] += 1
                continue
            transforms = {
                "business_id": business_map[row["business_id"]],
                "location_id": location_map[row["location_id"]],
                "wallet_id": wallet_map[row["wallet_id"]],
                "created_by_id": user_map[row["created_by_id"]],
                "tip_employee_id": user_map.get(row["tip_employee_id"]) if row["tip_employee_id"] else None,
                "purchase_entry_id": None,
                "tip_entry_id": None,
            }
            legacy_payment_links[old_id] = (row["purchase_entry_id"], row["tip_entry_id"])
            self._raw_insert(PaymentRequest, row, preserve_pk=True, transforms=transforms)
            payment_map[old_id] = old_id
            inserted_payment_ids.add(old_id)
            stats["payments_inserted"] += 1

        ledger_map = {}
        for row in self._legacy_rows(LedgerEntry):
            old_id = row["id"]
            mapped_business = business_map[row["business_id"]]
            q = Q(pk=old_id) | Q(bill_number=row["bill_number"])
            if row["idempotency_key"]:
                q |= Q(business_id=mapped_business, idempotency_key=row["idempotency_key"])
            candidate = self._one_candidate(LedgerEntry.objects.filter(q), f"Legacy-Ledger {old_id}")
            if candidate:
                ledger_map[old_id] = candidate
                if candidate != old_id:
                    stats["ledger_mapped_to_existing_identity"] += 1
                else:
                    stats["ledger_current_wins"] += 1
                continue
            self._raw_insert(
                LedgerEntry,
                row,
                preserve_pk=True,
                transforms={
                    "business_id": mapped_business,
                    "location_id": location_map.get(row["location_id"]) if row["location_id"] else None,
                    "wallet_id": wallet_map[row["wallet_id"]],
                    "payment_request_id": payment_map.get(row["payment_request_id"]) if row["payment_request_id"] else None,
                    "performed_by_id": user_map[row["performed_by_id"]],
                },
            )
            ledger_map[old_id] = old_id
            stats["ledger_inserted"] += 1

        # Only newly imported payments receive links from Legacy. Existing current payments are never overwritten.
        for payment_id in inserted_payment_ids:
            purchase_old, tip_old = legacy_payment_links.get(payment_id, (None, None))
            PaymentRequest.objects.filter(pk=payment_id).update(
                purchase_entry_id=ledger_map.get(purchase_old) if purchase_old else None,
                tip_entry_id=ledger_map.get(tip_old) if tip_old else None,
            )

        for row in self._legacy_rows(ReviewStatus):
            mapped_wallet = wallet_map[row["wallet_id"]]
            mapped_location = location_map[row["location_id"]]
            if not ReviewStatus.objects.filter(wallet_id=mapped_wallet, location_id=mapped_location).exists():
                self._insert_leaf(
                    ReviewStatus,
                    row,
                    transforms={"wallet_id": mapped_wallet, "location_id": mapped_location},
                )
                stats["review_statuses_inserted"] += 1

        for row in self._legacy_rows(TransactionCase):
            mapped_wallet = wallet_map[row["wallet_id"]]
            mapped_ledger = ledger_map[row["ledger_entry_id"]]
            candidate = self._one_candidate(
                TransactionCase.objects.filter(Q(pk=row["id"]) | Q(case_number=row["case_number"])),
                f"Legacy-TransactionCase {row['id']}",
            )
            if candidate:
                continue
            self._raw_insert(
                TransactionCase,
                row,
                preserve_pk=True,
                transforms={
                    "business_id": business_map[row["business_id"]],
                    "location_id": location_map.get(row["location_id"]) if row["location_id"] else None,
                    "wallet_id": mapped_wallet,
                    "ledger_entry_id": mapped_ledger,
                    "opened_by_id": user_map[row["opened_by_id"]],
                    "reviewed_by_id": user_map.get(row["reviewed_by_id"]) if row["reviewed_by_id"] else None,
                    "refund_entry_id": ledger_map.get(row["refund_entry_id"]) if row["refund_entry_id"] else None,
                },
            )
            stats["transaction_cases_inserted"] += 1

        for row in self._legacy_rows(AccountDeletionRequest):
            candidate = self._one_candidate(
                AccountDeletionRequest.objects.filter(Q(pk=row["id"]) | Q(reference_number=row["reference_number"])),
                f"Legacy-DeletionRequest {row['id']}",
            )
            if candidate:
                continue
            self._raw_insert(
                AccountDeletionRequest,
                row,
                preserve_pk=True,
                transforms={
                    "user_id": user_map.get(row["user_id"]) if row["user_id"] else None,
                    "business_id": business_map[row["business_id"]],
                    "wallet_id": wallet_map.get(row["wallet_id"]) if row["wallet_id"] else None,
                },
            )
            stats["deletion_requests_inserted"] += 1

        for row in self._legacy_rows(Offer):
            if Offer.objects.filter(pk=row["id"]).exists():
                continue
            self._raw_insert(
                Offer,
                row,
                preserve_pk=True,
                transforms={
                    "business_id": business_map[row["business_id"]],
                    "location_id": location_map.get(row["location_id"]) if row["location_id"] else None,
                    "created_by_id": user_map[row["created_by_id"]],
                },
            )
            stats["offers_inserted"] += 1

        # Notifications are history. Detect semantic duplicates first; if an integer PK was reused
        # by a newer current notification, retain both by assigning a new current PK to the legacy row.
        for row in self._legacy_rows(AppNotification):
            transforms = {
                "recipient_id": user_map[row["recipient_id"]],
                "business_id": business_map[row["business_id"]],
                "location_id": location_map.get(row["location_id"]) if row["location_id"] else None,
            }
            duplicate = AppNotification.objects.filter(
                recipient_id=transforms["recipient_id"],
                business_id=transforms["business_id"],
                location_id=transforms["location_id"],
                kind=row["kind"],
                title=row["title"],
                body=row["body"],
                data=row["data"],
                created_at=row["created_at"],
            ).exists()
            if duplicate:
                continue
            self._insert_leaf(AppNotification, row, transforms=transforms)
            stats["notifications_inserted"] += 1

        for row in self._legacy_rows(PushDevice):
            mapped_user = user_map[row["user_id"]]
            if PushDevice.objects.filter(token=row["token"]).exists():
                continue
            self._insert_leaf(PushDevice, row, transforms={"user_id": mapped_user})
            stats["push_devices_inserted"] += 1

        for row in self._legacy_rows(AuditEvent):
            transforms = {
                "actor_id": user_map.get(row["actor_id"]) if row["actor_id"] else None,
                "business_id": business_map[row["business_id"]],
            }
            duplicate = AuditEvent.objects.filter(
                actor_id=transforms["actor_id"],
                business_id=transforms["business_id"],
                action=row["action"],
                object_type=row["object_type"],
                object_id=row["object_id"],
                details=row["details"],
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            ).exists()
            if duplicate:
                continue
            self._insert_leaf(AuditEvent, row, transforms=transforms)
            stats["audit_events_inserted"] += 1

        for row in self._legacy_rows(TestWalletMarker):
            mapped_wallet = wallet_map[row["wallet_id"]]
            if TestWalletMarker.objects.filter(wallet_id=mapped_wallet).exists():
                continue
            self._insert_leaf(
                TestWalletMarker,
                row,
                transforms={
                    "wallet_id": mapped_wallet,
                    "marked_by_id": user_map.get(row["marked_by_id"]) if row["marked_by_id"] else None,
                },
            )
            stats["test_wallet_markers_inserted"] += 1

        stats["legacy_users_total"] = len(user_map)
        stats["legacy_wallets_total"] = len(wallet_map)
        stats["legacy_payments_total"] = len(payment_map)
        stats["legacy_ledger_total"] = len(ledger_map)
        return stats

    def _reset_sequences(self):
        User = get_user_model()
        models = [
            User,
            Group,
            EmailAddress,
            SocialAccount,
            Business,
            BusinessSettings,
            Membership,
            MemberProfile,
            LocationVisual,
            LegalConfiguration,
            LegalAcceptance,
            PrivacyPreference,
            ReviewStatus,
            AppNotification,
            PushDevice,
            AuditEvent,
            TestWalletMarker,
        ]
        sql_list = connection.ops.sequence_reset_sql(no_style(), models)
        with connection.cursor() as cursor:
            for sql in sql_list:
                cursor.execute(sql)

    def _validate(self, stats):
        User = get_user_model()
        legacy_user_ids = set(User.objects.using("legacy").values_list("pk", flat=True))
        current_user_ids = set(User.objects.filter(pk__in=legacy_user_ids).values_list("pk", flat=True))
        if legacy_user_ids != current_user_ids:
            raise CommandError(f"Nach Merge fehlen {len(legacy_user_ids-current_user_ids)} Legacy-User-PKs.")

        if stats["legacy_wallets_total"] != Wallet.objects.using("legacy").count():
            raise CommandError("Wallet-Mapping ist unvollständig.")
        if stats["legacy_payments_total"] != PaymentRequest.objects.using("legacy").count():
            raise CommandError("Payment-Mapping ist unvollständig.")
        if stats["legacy_ledger_total"] != LedgerEntry.objects.using("legacy").count():
            raise CommandError("Ledger-Mapping ist unvollständig.")

        # Every legacy member profile, privacy preference, legal acceptance and review row must now
        # have a logical counterpart in Current, even when a Wallet UUID was mapped to a newer UUID.
        legacy_profile_users = set(MemberProfile.objects.using("legacy").values_list("user_id", flat=True))
        current_profile_users = set(MemberProfile.objects.filter(user_id__in=legacy_profile_users).values_list("user_id", flat=True))
        if legacy_profile_users - current_profile_users:
            raise CommandError("Mindestens ein Legacy-Mitgliederprofil fehlt nach dem Merge.")

        self.stdout.write(
            "POST_COUNTS "
            f"users={User.objects.count()} "
            f"wallets={Wallet.objects.count()} "
            f"profiles={MemberProfile.objects.count()} "
            f"privacy={PrivacyPreference.objects.count()} "
            f"legal={LegalAcceptance.objects.count()} "
            f"reviews={ReviewStatus.objects.count()} "
            f"push_devices={PushDevice.objects.count()} "
            f"payments={PaymentRequest.objects.count()} "
            f"ledger={LedgerEntry.objects.count()}"
        )
