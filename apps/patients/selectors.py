"""Permission-driven query helpers for the patients module.

The row-level decision (who may see full contact details) lives here only.
"""
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from core.permissions import PATIENT_VIEW, PATIENT_VIEW_CONTACT, user_has_permission

from .models import Patient, mask_phone


def visible_patients(user: Any) -> QuerySet[Patient]:
    """Active patients for users holding patient.view; empty set otherwise."""
    if not user_has_permission(user, PATIENT_VIEW):
        return Patient.objects.none()
    return Patient.objects.all()


def get_visible_patient(pk: int, user: Any, request: HttpRequest | None = None) -> Patient:
    """One patient or a hard 404; row-level rule enforced for every viewer."""
    return get_object_or_404(visible_patients(user), pk=pk)


def require_view_contact(user: Any, request: HttpRequest | None = None) -> None:
    """Raise when the viewer may see unmasked phone/contact details."""
    if not user_has_permission(user, PATIENT_VIEW_CONTACT, request=request):
        raise PermissionDenied("Full contact details are restricted.")


def display_phone(patient: Patient, user: Any) -> str:
    """Masked phone for viewers without patient.view_contact."""
    if user_has_permission(user, PATIENT_VIEW_CONTACT):
        return patient.phone or "—"
    return mask_phone(patient.phone)
