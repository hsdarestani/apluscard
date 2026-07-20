from decimal import Decimal

from django import forms

from .models import Wallet


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
