from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import BusinessSettings, Location, MemberProfile, Offer, Wallet


def validate_adult_birth_date(birth_date):
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if age < 18:
        raise forms.ValidationError("Die Registrierung ist erst ab 18 Jahren möglich.")
    return birth_date


class CustomerRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Vorname", max_length=150)
    last_name = forms.CharField(label="Nachname", max_length=150)
    email = forms.EmailField(label="E-Mail-Adresse", max_length=150)
    phone = forms.CharField(label="Mobilnummer", max_length=40)
    birth_date = forms.DateField(label="Geburtsdatum", widget=forms.DateInput(attrs={"type": "date"}))
    age_confirmed = forms.BooleanField(label="Ich bestätige, dass ich mindestens 18 Jahre alt bin.", required=True)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Für diese E-Mail-Adresse besteht bereits ein Konto.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if len(phone) < 6:
            raise forms.ValidationError("Bitte eine gültige Mobilnummer eingeben.")
        return phone

    def clean_birth_date(self):
        return validate_adult_birth_date(self.cleaned_data["birth_date"])

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            user.save()
        return user


class AppleProfileCompletionForm(forms.Form):
    first_name = forms.CharField(label="Vorname", max_length=150)
    last_name = forms.CharField(label="Nachname", max_length=150)
    phone = forms.CharField(label="Mobilnummer", max_length=40)
    birth_date = forms.DateField(label="Geburtsdatum", widget=forms.DateInput(attrs={"type": "date"}))
    age_confirmed = forms.BooleanField(label="Ich bestätige, dass ich mindestens 18 Jahre alt bin.", required=True)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        initial = kwargs.setdefault("initial", {})
        if user is not None:
            initial.setdefault("first_name", user.first_name)
            initial.setdefault("last_name", user.last_name)
            profile = getattr(user, "member_profile", None)
            if profile and profile.birth_date:
                initial.setdefault("birth_date", profile.birth_date)
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if len(phone) < 6:
            raise forms.ValidationError("Bitte eine gültige Mobilnummer eingeben.")
        return phone

    def clean_birth_date(self):
        return validate_adult_birth_date(self.cleaned_data["birth_date"])

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()
        self.user.save(update_fields=["first_name", "last_name"])
        MemberProfile.objects.update_or_create(
            user=self.user,
            defaults={
                "birth_date": self.cleaned_data["birth_date"],
                "age_confirmed": True,
                "email_verified": True,
                "email_verified_at": timezone.now(),
            },
        )
        return self.user


class MoneyActionForm(forms.Form):
    wallet_token = forms.UUIDField(label="Kartencode")
    location_id = forms.UUIDField(label="Standort")
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    tip_amount = forms.DecimalField(label="Trinkgeld in Euro", min_value=Decimal("0.00"), max_value=Decimal("100.00"), max_digits=8, decimal_places=2, required=False)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Bestellnummer", max_length=100, required=False)


class PaymentConfirmForm(forms.Form):
    tip_amount = forms.DecimalField(label="Trinkgeld in Euro", min_value=Decimal("0.00"), max_value=Decimal("100.00"), max_digits=8, decimal_places=2)


class ManagerMoneyActionForm(forms.Form):
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Referenz", max_length=100, required=False)


class ManagerChargeForm(ManagerMoneyActionForm):
    location_id = forms.UUIDField(label="Standort")
    tip_amount = forms.DecimalField(label="Trinkgeld in Euro", min_value=Decimal("0.00"), max_value=Decimal("100.00"), max_digits=8, decimal_places=2, required=False)


class WalletCreateForm(forms.ModelForm):
    class Meta:
        model = Wallet
        fields = ["display_name", "phone", "email"]
        labels = {"display_name": "Name", "phone": "Telefon", "email": "E-Mail-Adresse"}


class BusinessSettingsForm(forms.ModelForm):
    class Meta:
        model = BusinessSettings
        fields = ["require_customer_confirmation", "tip_option_1", "tip_option_2", "tip_option_3", "tip_option_4", "tip_allocation", "gold_threshold", "platinum_threshold", "birthday_bonus", "daily_summary_enabled", "weekly_summary_enabled", "offer_scheduling_enabled", "official_invoice_enabled", "legal_name", "legal_address", "tax_number", "vat_id"]
        labels = {
            "require_customer_confirmation": "Ausnahmsweise Bestätigung durch den Kunden verlangen",
            "tip_option_1": "Trinkgeldoption 1 (€)",
            "tip_option_2": "Trinkgeldoption 2 (€)",
            "tip_option_3": "Trinkgeldoption 3 (€)",
            "tip_option_4": "Trinkgeldoption 4 (€)",
            "tip_allocation": "Zuordnung des Trinkgelds",
            "gold_threshold": "Grenze für Gold",
            "platinum_threshold": "Grenze für Platin",
            "birthday_bonus": "Geburtstagsbonus",
            "daily_summary_enabled": "Tägliche Zusammenfassung aktivieren",
            "weekly_summary_enabled": "Wöchentliche Zusammenfassung aktivieren",
            "offer_scheduling_enabled": "Zeitraum für Angebote verwenden",
            "official_invoice_enabled": "Offizielle Rechnung aktivieren",
            "legal_name": "Rechtlicher Firmenname",
            "legal_address": "Geschäftsanschrift",
            "tax_number": "Steuernummer",
            "vat_id": "Umsatzsteuer-Identifikationsnummer",
        }
        widgets = {
            "legal_address": forms.Textarea(attrs={"rows": 3}),
            "tip_option_1": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.50"}),
            "tip_option_2": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.50"}),
            "tip_option_3": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.50"}),
            "tip_option_4": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.50"}),
        }

    def clean(self):
        cleaned = super().clean()
        gold = cleaned.get("gold_threshold")
        platinum = cleaned.get("platinum_threshold")
        if gold is not None and platinum is not None and platinum <= gold:
            self.add_error("platinum_threshold", "Die Platin-Grenze muss über der Gold-Grenze liegen.")
        tip_values = []
        for field in ("tip_option_1", "tip_option_2", "tip_option_3", "tip_option_4"):
            value = cleaned.get(field)
            if value is not None and (value < 0 or value > 100):
                self.add_error(field, "Der Betrag muss zwischen 0 und 100 Euro liegen.")
            if value is not None:
                tip_values.append(value)
        if len(tip_values) != len(set(tip_values)):
            self.add_error("tip_option_4", "Jede Trinkgeldoption muss einen eigenen Betrag haben.")
        return cleaned


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "slug", "address", "google_review_url", "instagram_url", "tiktok_url", "is_active", "position"]
        labels = {
            "name": "Name",
            "slug": "Kurzname",
            "address": "Adresse",
            "google_review_url": "Link zur Google-Bewertung",
            "instagram_url": "Instagram-Link",
            "tiktok_url": "TikTok-Link",
            "is_active": "Aktiv",
            "position": "Reihenfolge",
        }
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["location", "title", "body", "image", "target_tier", "is_active", "starts_at", "ends_at"]
        labels = {
            "location": "Standort",
            "title": "Titel",
            "body": "Beschreibung",
            "image": "Bild",
            "target_tier": "Zielstufe",
            "is_active": "Aktiv",
            "starts_at": "Beginn (optional)",
            "ends_at": "Ende (optional)",
        }
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4}),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, business=None, scheduling_enabled=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.none()
        self.fields["starts_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        if business is not None:
            self.fields["location"].queryset = business.locations.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "Das Ende muss nach dem Beginn liegen.")
        return cleaned


class WalletLookupForm(forms.Form):
    query = forms.CharField(label="Mitglied oder Kartencode", max_length=140)
