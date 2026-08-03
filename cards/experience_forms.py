from decimal import Decimal

from django import forms

from .experience_models import LocationVisual, TransactionCase
from .models import Location


class LocationVisualForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 10 * 1024 * 1024
    ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF", "HEIF", "HEIC"}

    location = forms.ModelChoiceField(label="Standort", queryset=Location.objects.none())
    image = forms.ImageField(
        label="Foto des Standorts",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "accept": (
                    "image/jpeg,image/png,image/webp,image/avif,image/heic,image/heif,"
                    ".jpg,.jpeg,.png,.webp,.avif,.heic,.heif"
                )
            }
        ),
        error_messages={
            "invalid_image": (
                "Die Datei konnte nicht als Bild gelesen werden. "
                "Bitte ein JPG-, PNG-, WebP-, AVIF- oder HEIC/HEIF-Bild verwenden."
            ),
        },
    )
    short_description = forms.CharField(
        label="Kurze Beschreibung",
        required=False,
        max_length=180,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Optional, z. B. Lounge, Shisha und Sportübertragungen"
            }
        ),
    )

    class Meta:
        model = LocationVisual
        fields = ["location", "image", "short_description"]

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        if business is not None:
            self.fields["location"].queryset = business.locations.filter(is_active=True)

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        if image.size > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError(
                "Das Bild ist größer als 10 MB. Bitte das Bild verkleinern und erneut hochladen."
            )

        detected_format = str(
            getattr(getattr(image, "image", None), "format", "") or ""
        ).upper()
        if detected_format not in self.ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError(
                "Dieses Bildformat wird nicht unterstützt. Bitte JPG, PNG, WebP, AVIF oder HEIC/HEIF verwenden."
            )

        try:
            image.seek(0)
        except (AttributeError, OSError):
            pass
        return image

    def save(self, commit=True):
        location = self.cleaned_data["location"]
        visual, _ = LocationVisual.objects.get_or_create(location=location)
        visual.image = self.cleaned_data.get("image") or visual.image
        visual.short_description = self.cleaned_data.get("short_description", "").strip()
        if commit:
            visual.save()
        return visual


class TransactionCaseForm(forms.Form):
    reason = forms.ChoiceField(label="Grund", choices=TransactionCase.Reason.choices)
    description = forms.CharField(
        label="Was ist passiert?",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Bitte den Fehler möglichst genau beschreiben."}),
        min_length=8,
        max_length=2000,
    )
    requested_amount = forms.DecimalField(
        label="Gewünschter Erstattungsbetrag",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Optional. Eine Erstattung wird erst nach Prüfung durch den Inhaber gebucht.",
    )

    def __init__(self, *args, ledger_entry=None, **kwargs):
        self.ledger_entry = ledger_entry
        super().__init__(*args, **kwargs)
        if ledger_entry is not None and ledger_entry.amount < 0:
            self.fields["requested_amount"].initial = abs(ledger_entry.amount)
        elif ledger_entry is not None:
            self.fields["requested_amount"].widget = forms.HiddenInput()

    def clean_requested_amount(self):
        amount = self.cleaned_data.get("requested_amount")
        if amount is None or self.ledger_entry is None:
            return amount
        if self.ledger_entry.amount >= 0:
            raise forms.ValidationError("Für diese Buchung ist keine automatische Erstattung möglich.")
        if amount > abs(self.ledger_entry.amount):
            raise forms.ValidationError("Der Betrag darf die ursprüngliche Belastung nicht überschreiten.")
        return amount


class TransactionCaseReviewForm(forms.Form):
    action = forms.ChoiceField(
        label="Entscheidung",
        choices=[
            (TransactionCase.Status.IN_REVIEW, "In Prüfung setzen"),
            (TransactionCase.Status.APPROVED, "Genehmigen und erstatten"),
            (TransactionCase.Status.REJECTED, "Ablehnen"),
        ],
    )
    approved_amount = forms.DecimalField(
        label="Erstattungsbetrag",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    manager_note = forms.CharField(
        label="Mitteilung zur Entscheidung",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
        max_length=2000,
    )

    def __init__(self, *args, transaction_case=None, **kwargs):
        self.transaction_case = transaction_case
        super().__init__(*args, **kwargs)
        if transaction_case and transaction_case.requested_amount:
            self.fields["approved_amount"].initial = transaction_case.requested_amount
        elif transaction_case and transaction_case.refundable_amount:
            self.fields["approved_amount"].initial = transaction_case.refundable_amount

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        amount = cleaned.get("approved_amount")
        if action == TransactionCase.Status.APPROVED:
            if not self.transaction_case or self.transaction_case.ledger_entry.amount >= 0:
                self.add_error("action", "Diese Buchung kann nicht automatisch erstattet werden.")
            if amount is None:
                self.add_error("approved_amount", "Bitte den Erstattungsbetrag angeben.")
            elif self.transaction_case and amount > abs(self.transaction_case.ledger_entry.amount):
                self.add_error("approved_amount", "Der Betrag darf die ursprüngliche Belastung nicht überschreiten.")
        return cleaned
