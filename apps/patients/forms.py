"""ModelForms for patient registration and contacts."""
import datetime

from django import forms
from django.utils import timezone

from .models import EmergencyContact, Patient


class PatientForm(forms.ModelForm):
    """Registration / edit form; required fields stay short, extras collapse."""

    class Meta:
        model = Patient
        fields = (
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "phone",
            "email",
            "address",
            "city",
            "state",
            "postal_code",
            "blood_group",
            "known_allergies",
        )
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "known_allergies": forms.Textarea(attrs={"rows": 2}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "known_allergies": "Known allergies",
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        optional = {
            "email", "address", "city", "state", "postal_code",
            "blood_group", "known_allergies",
        }
        more_details = {"address", "city", "state", "postal_code"}
        for name, field in self.fields.items():
            field.required = name not in optional
            if name in more_details and not (self.instance and self.instance.pk):
                field.help_text = "Optional — part of “More details”."

    def clean_date_of_birth(self) -> datetime.date:
        dob = self.cleaned_data["date_of_birth"]
        if dob and dob > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return dob

    def clean_email(self) -> str:
        return (self.cleaned_data.get("email") or "").casefold().strip()


class EmergencyContactForm(forms.ModelForm):
    """Add-on form on the patient detail page."""

    class Meta:
        model = EmergencyContact
        fields = ("name", "relationship", "phone", "is_primary")

    def clean_name(self) -> str:
        return (self.cleaned_data.get("name") or "").strip()

    def clean_relationship(self) -> str:
        return (self.cleaned_data.get("relationship") or "").strip()
