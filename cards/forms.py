from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Wallet


class CustomerRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Vorname", max_length=150)
    last_name = forms.CharField(label="Nachname", max_length=150)
    email = forms.EmailField(label="E-Mail-Adresse", max_length=150)
    phone = forms.CharField(label="Mobilnummer", max_length=40)

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
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Bestellnummer", max_length=100, required=False)


class ManagerMoneyActionForm(forms.Form):
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Referenz", max_length=100, required=False)


class WalletCreateForm(forms.ModelForm):
    class Meta:
        model = Wallet
        fields = ["display_name", "phone", "email"]
        labels = {"display_name": "Name", "phone": "Telefon", "email": "E-Mail"}


class WalletLookupForm(forms.Form):
    query = forms.CharField(label="Kunde oder Kartencode", max_length=140)
