"""Patient write operations: registration, duplicate detection, contacts."""
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.audit.models import AuditLog
from apps.audit.utils import log_to_audit

from .models import EmergencyContact, Patient


def find_duplicate_patients(first_name: str, last_name: str, date_of_birth: Any, phone: str) -> QuerySet[Patient]:
    """Same name + DOB + phone heuristic (see PatientForm for the message)."""
    return Patient.objects.filter(
        first_name__iexact=first_name.strip(),
        last_name__iexact=last_name.strip(),
        date_of_birth=date_of_birth,
        phone=phone.strip(),
    )


@transaction.atomic
def create_patient(*, form: Any, user: Any) -> Patient:
    """Persist a new patient inside one transaction and audit the creation."""
    patient = form.save(commit=False)
    patient.created_by = user
    patient.save()
    form.save_m2m()  # ModelForm without M2M: kept for future fields
    log_to_audit(
        user=user,
        action=AuditLog.Action.CREATE,
        object_type="patient",
        object_id=patient.patient_code,
        details=f"Registered patient {patient.full_name}",
    )
    return patient


@transaction.atomic
def update_patient(*, patient: Patient, form: Any, user: Any) -> Patient:
    """Persist patient edits and audit them."""
    form.save()
    log_to_audit(
        user=user,
        action=AuditLog.Action.UPDATE,
        object_type="patient",
        object_id=patient.patient_code,
        details=f"Edited patient {patient.full_name}",
    )
    return patient


@transaction.atomic
def archive_patient(*, patient: Patient, user: Any) -> None:
    """Soft-delete a patient (Super Admin only); appointments remain linked."""
    details = f"Archived patient {patient.patient_code} {patient.full_name}"
    patient.soft_delete(user=user)
    log_to_audit(
        user=user,
        action=AuditLog.Action.DELETE,
        object_type="patient",
        object_id=patient.patient_code,
        details=details,
    )


@transaction.atomic
def add_contact(
    *, patient: Patient, form: Any, user: Any, ip: str | None = None
) -> EmergencyContact:
    """Add an emergency contact, making it primary when asked."""
    contact = form.save(commit=False)
    contact.patient = patient
    if contact.is_primary:
        patient.contacts.filter(is_primary=True).update(is_primary=False)
    contact.save()
    log_to_audit(
        user=user,
        action=AuditLog.Action.CREATE,
        object_type="patient_contact",
        object_id=patient.patient_code,
        details=f"Added contact {contact.name} ({contact.relationship})",
    )
    return contact


@transaction.atomic
def make_contact_primary(*, contact: EmergencyContact, user: Any, ip: str | None = None) -> None:
    """Move the primary flag; the side effect cascades inside one transaction."""
    contact.patient.contacts.filter(is_primary=True).update(is_primary=False)
    contact.is_primary = True
    contact.save(update_fields=["is_primary"])
    log_to_audit(
        user=user,
        action=AuditLog.Action.UPDATE,
        object_type="patient_contact",
        object_id=contact.patient.patient_code,
        details=f"Made contact {contact.name} primary",
    )


def log_patient_view(*, patient: Patient, user: Any, request: Any) -> None:
    """Log VIEW for medical privacy on every patient record read."""
    log_to_audit(
        user=user,
        action=AuditLog.Action.VIEW,
        request=request,
        object_type="patient",
        object_id=patient.patient_code,
        details=f"Viewed patient {patient.full_name}",
    )
