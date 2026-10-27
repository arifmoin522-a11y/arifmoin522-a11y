"""Patient records: demographics, contacts and privacy helpers.

All behaviour is permission-driven; phone masking and history access never
look at role names.
"""
from typing import Any

from django.conf import settings
from django.core.validators import EmailValidator, RegexValidator, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel, next_sequence_value

from .constants import SEQUENCE_PATIENT, BloodGroup, Gender

def _format_code(prefix: str, value: int) -> str:
    """Human code from the env-driven prefix and zero-padded digit count."""
    return f"{prefix}-{value:0{settings.CODE_SEQUENCE_DIGITS}d}"


class Patient(BaseModel):
    """A registered patient (demographics only; no clinical content in Phase 2)."""

    patient_code = models.CharField(max_length=32, unique=True, editable=False)
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=4, choices=Gender.choices, default=Gender.NOT_STATED
    )
    phone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                settings.PHONE_REGEX,
                _("Phone must be 7-20 digits; +, spaces and dashes are allowed."),
            )
        ],
    )
    email = models.EmailField(blank=True, validators=[EmailValidator()])
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, blank=True)
    postal_code = models.CharField(max_length=16, blank=True)
    blood_group = models.CharField(
        max_length=3, choices=BloodGroup.choices, blank=True, default=""
    )
    known_allergies = models.TextField(blank=True)
    registered_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-registered_at"]
        indexes = [
            models.Index(fields=["first_name", "last_name"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["date_of_birth"]),
        ]

    def __str__(self) -> str:
        return f"{self.patient_code} {self.first_name} {self.last_name}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age_years(self) -> int | None:
        today = timezone.localdate()
        born = self.date_of_birth
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    @property
    def blood_group_display(self) -> str:
        return self.get_blood_group_display() or "—"

    @property
    def primary_contact(self) -> "EmergencyContact | None":
        for contact in self.contacts.all():
            if contact.is_primary:
                return contact
        return None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Allocate the unique patient_code inside the current transaction."""
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            raise ValidationError({
                "date_of_birth": "Date of birth cannot be in the future."
            })
        if not self.patient_code:
            value = next_sequence_value(
                SEQUENCE_PATIENT, start=settings.CODE_SEQUENCE_START
            )
            self.patient_code = _format_code(settings.PATIENT_CODE_PREFIX, value)
        if self.email:
            self.email = self.email.casefold().strip()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})


class EmergencyContact(models.Model):
    """Someone to call about the patient; exactly one primary per patient."""

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField(max_length=128)
    relationship = models.CharField(max_length=64)
    phone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                settings.PHONE_REGEX,
                _("Phone must be 7-20 digits; +, spaces and dashes are allowed."),
            )
        ],
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient"],
                condition=models.Q(is_primary=True),
                name="one_primary_contact_per_patient",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.relationship})"


def mask_phone(phone: str) -> str:
    """Show only the last 3 digits; used in list views without contact permission."""
    if not phone:
        return "—"
    return "*" * max(len(phone) - 3, 0) + phone[-3:]
