from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import BusinessSettings, Location, Offer, Wallet


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
        birth_date = self.cleaned_data["birth_date"]
        today = date.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        if age < 18:
            raise forms.ValidationError("Die Registrierung ist erst ab 18 Jahren möglich.")
        return birth_date

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            user.save()
        return user


class MoneyActionForm(forms.Form):
    wallet_token = forms.UUIDField(label="Kartencode")
    location_id = forms.UUIDField(label="Standort")
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    tip_percentage = forms.DecimalField(label="Trinkgeld", min_value=Decimal("0.00"), max_value=Decimal("100.00"), max_digits=5, decimal_places=2, required=False)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Bestellnummer", max_length=100, required=False)


class PaymentConfirmForm(forms.Form):
    tip_percentage = forms.DecimalField(label="Trinkgeld", min_value=Decimal("0.00"), max_value=Decimal("100.00"), max_digits=5, decimal_places=2)


class ManagerMoneyActionForm(forms.Form):
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Referenz", max_length=100, required=False)


class WalletCreateForm(forms.ModelForm):
    class Meta:
        model = Wallet
        fields = ["display_name", "phone", "email"]
        labels = {"display_name": "Name", "phone": "Telefon", "email": "E-Mail"}


class BusinessSettingsForm(forms.ModelForm):
    class Meta:
        model = BusinessSettings
        fields = ["require_customer_confirmation", "tip_option_1", "tip_option_2", "tip_option_3", "tip_option_4", "tip_allocation", "gold_threshold", "platinum_threshold", "birthday_bonus", "daily_summary_enabled", "weekly_summary_enabled", "offer_scheduling_enabled", "official_invoice_enabled", "legal_name", "legal_address", "tax_number", "vat_id"]
        widgets = {"legal_address": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        cleaned = super().clean()
        gold = cleaned.get("gold_threshold")
        platinum = cleaned.get("platinum_threshold")
        if gold is not None and platinum is not None and platinum <= gold:
            self.add_error("platinum_threshold", "Platinum muss über der Gold-Grenze liegen.")
        for field in ("tip_option_1", "tip_option_2", "tip_option_3", "tip_option_4"):
            value = cleaned.get(field)
            if value is not None and (value < 0 or value > 100):
                self.add_error(field, "Der Wert muss zwischen 0 und 100 Prozent liegen.")
        return cleaned


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "slug", "address", "google_review_url", "instagram_url", "tiktok_url", "is_active", "position"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["location", "title", "body", "image", "target_tier", "is_active", "starts_at", "ends_at"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4}), "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, business=None, scheduling_enabled=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.none()
        if business is not None:
            self.fields["location"].queryset = business.locations.filter(is_active=True)
        if not scheduling_enabled:
            self.fields["starts_at"].widget = forms.HiddenInput()
            self.fields["ends_at"].widget = forms.HiddenInput()
            self.fields["starts_at"].required = False
            self.fields["ends_at"].required = False


class WalletLookupForm(forms.Form):
    query = forms.CharField(label="Kunde oder Kartencode", max_length=140)
