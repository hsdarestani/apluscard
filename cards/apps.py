from django.apps import AppConfig


class CardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cards"
    verbose_name = "SAMS Verwaltung"

    def import_models(self):
        super().import_models()
        # Zusätzliche Modellgruppen gehören weiterhin zur Django-App `cards`.
        from . import experience_models, legal_models, push_models  # noqa: F401

    def ready(self):
        from . import experience_signals  # noqa: F401
        from .experience_models import LocationVisual, MemberNumberSequence, TransactionCase
        from .models import (
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
        from .push_models import PushDelivery

        translated_choices = {
            (Membership, "role"): [("OWNER", "Inhaber"), ("MANAGER", "Leitung"), ("STAFF", "Mitarbeiter")],
            (Wallet, "status"): [("ACTIVE", "Aktiv"), ("BLOCKED", "Gesperrt"), ("CLOSED", "Geschlossen")],
            (Wallet, "tier"): [("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platin")],
            (LedgerEntry, "entry_type"): [
                ("TOPUP", "Aufladung"),
                ("PURCHASE", "Zahlung"),
                ("TIP", "Trinkgeld"),
                ("REFUND", "Erstattung"),
                ("BONUS", "Bonus"),
                ("ADJUSTMENT", "Korrektur"),
            ],
            (Offer, "target_tier"): [("ALL", "Alle"), ("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platin")],
            (PushDevice, "platform"): [("IOS", "iOS"), ("ANDROID", "Android"), ("WEB", "Browser")],
        }
        for (model, field_name), choices in translated_choices.items():
            model._meta.get_field(field_name).choices = choices

        model_names = {
            Business: ("Betrieb", "Betriebe"),
            Location: ("Standort", "Standorte"),
            LocationVisual: ("Standortbild", "Standortbilder"),
            BusinessSettings: ("Betriebseinstellung", "Betriebseinstellungen"),
            Membership: ("Berechtigung", "Berechtigungen"),
            MemberProfile: ("Mitgliederprofil", "Mitgliederprofile"),
            Wallet: ("Mitgliedsguthaben", "Mitgliedsguthaben"),
            MemberNumberSequence: ("Nummernkreis", "Nummernkreise"),
            PaymentRequest: ("Zahlungsanfrage", "Zahlungsanfragen"),
            LedgerEntry: ("Transaktion", "Transaktionen"),
            TransactionCase: ("Transaktionsfall", "Transaktionsfälle"),
            Offer: ("Angebot", "Angebote"),
            ReviewStatus: ("Bewertungsstatus", "Bewertungsstatus"),
            AppNotification: ("Mitteilung", "Mitteilungen"),
            PushDevice: ("Gerät für Mitteilungen", "Geräte für Mitteilungen"),
            PushDelivery: ("Push-Zustellung", "Push-Zustellungen"),
            AuditEvent: ("Prüfprotokoll", "Prüfprotokolle"),
        }
        for model, (singular, plural) in model_names.items():
            model._meta.verbose_name = singular
            model._meta.verbose_name_plural = plural
