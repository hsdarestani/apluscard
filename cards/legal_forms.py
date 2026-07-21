from django import forms

from .forms import AppleProfileCompletionForm, CustomerRegistrationForm
from .legal_models import AccountDeletionRequest, LegalConfiguration, PrivacyPreference


class LegalAgreementFieldsMixin:
    accept_terms = forms.BooleanField(
        label="Ich akzeptiere die Allgemeinen Geschäftsbedingungen.",
        required=True,
    )
    acknowledge_privacy = forms.BooleanField(
        label="Ich habe die Datenschutzerklärung gelesen.",
        required=True,
    )
    marketing_push_consent = forms.BooleanField(
        label="Ich möchte freiwillig Push-Mitteilungen zu Angeboten und Aktionen erhalten.",
        required=False,
    )
    marketing_email_consent = forms.BooleanField(
        label="Ich möchte freiwillig E-Mails zu Angeboten und Aktionen erhalten.",
        required=False,
    )


class LegalCustomerRegistrationForm(LegalAgreementFieldsMixin, CustomerRegistrationForm):
    pass


class LegalAppleProfileCompletionForm(LegalAgreementFieldsMixin, AppleProfileCompletionForm):
    pass


class CurrentLegalAcceptanceForm(forms.Form):
    accept_terms = forms.BooleanField(
        label="Ich akzeptiere die aktuell geltenden Allgemeinen Geschäftsbedingungen.",
        required=True,
    )
    acknowledge_privacy = forms.BooleanField(
        label="Ich habe die aktuelle Datenschutzerklärung gelesen.",
        required=True,
    )


class PrivacyChoicesForm(forms.ModelForm):
    class Meta:
        model = PrivacyPreference
        fields = ["marketing_push_enabled", "marketing_email_enabled"]
        labels = {
            "marketing_push_enabled": "Push-Mitteilungen zu Angeboten und Aktionen",
            "marketing_email_enabled": "E-Mails zu Angeboten und Aktionen",
        }


class AccountDeletionRequestForm(forms.ModelForm):
    confirmation = forms.BooleanField(
        label="Ich bestätige, dass ich die Löschung meines Kontos und meiner personenbezogenen Kontodaten beantragen möchte.",
        required=True,
    )

    class Meta:
        model = AccountDeletionRequest
        fields = ["email", "member_number", "reason"]
        labels = {
            "email": "E-Mail-Adresse des Kontos",
            "member_number": "Mitgliedsnummer",
            "reason": "Zusätzliche Nachricht (optional)",
        }
        widgets = {"reason": forms.Textarea(attrs={"rows": 4})}

    def clean_member_number(self):
        return self.cleaned_data.get("member_number", "").strip()


class LegalConfigurationForm(forms.ModelForm):
    class Meta:
        model = LegalConfiguration
        fields = [
            "app_display_name",
            "controller_name",
            "controller_address",
            "representative",
            "contact_email",
            "privacy_email",
            "contact_phone",
            "register_court",
            "register_number",
            "vat_id",
            "data_protection_officer",
            "supervisory_authority",
            "terms_version",
            "terms_effective_date",
            "privacy_version",
            "privacy_effective_date",
            "terms_additional_clauses",
            "privacy_additional_information",
            "is_published",
        ]
        labels = {
            "app_display_name": "Öffentlicher App-Name",
            "controller_name": "Verantwortliches Unternehmen",
            "controller_address": "Vollständige Geschäftsanschrift",
            "representative": "Vertretungsberechtigte Person",
            "contact_email": "Allgemeine Kontakt-E-Mail",
            "privacy_email": "Datenschutz-E-Mail",
            "contact_phone": "Telefon",
            "register_court": "Registergericht",
            "register_number": "Registernummer",
            "vat_id": "Umsatzsteuer-Identifikationsnummer",
            "data_protection_officer": "Datenschutzbeauftragter (falls vorhanden)",
            "supervisory_authority": "Zuständige Datenschutzaufsichtsbehörde",
            "terms_version": "AGB-Version",
            "terms_effective_date": "AGB gültig ab",
            "privacy_version": "Datenschutz-Version",
            "privacy_effective_date": "Datenschutz gültig ab",
            "terms_additional_clauses": "Zusätzliche AGB-Klauseln für diese App",
            "privacy_additional_information": "Zusätzliche Datenschutzhinweise für diese App",
            "is_published": "Rechtstexte veröffentlicht",
        }
        widgets = {
            "controller_address": forms.Textarea(attrs={"rows": 3}),
            "data_protection_officer": forms.Textarea(attrs={"rows": 3}),
            "terms_effective_date": forms.DateInput(attrs={"type": "date"}),
            "privacy_effective_date": forms.DateInput(attrs={"type": "date"}),
            "terms_additional_clauses": forms.Textarea(attrs={"rows": 7}),
            "privacy_additional_information": forms.Textarea(attrs={"rows": 7}),
        }
