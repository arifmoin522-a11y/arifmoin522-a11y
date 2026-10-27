"""Patient views: search, register (with duplicate guard), detail, contacts.

Privacy: the search term travels via POST + a short-lived session key, never
in URLs or access logs. Rows keep patient codes in links only.
"""
from typing import Any

from django.contrib import messages
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import permissions as perms
from core.decorators import permission_required_code
from core.permissions import user_has_permission

from .forms import EmergencyContactForm, PatientForm
from .models import EmergencyContact, Patient
from .selectors import display_phone, get_visible_patient, visible_patients
from .services import (
    add_contact,
    archive_patient,
    create_patient,
    find_duplicate_patients,
    log_patient_view,
    make_contact_primary,
    update_patient,
)

#: session key holding the last search term (never part of a URL)
SEARCH_KEY = "patient_search_q"


def _page(request: HttpRequest, queryset: QuerySet[Patient]) -> Any:
    """Pagination honouring the env-driven page size."""
    from django.conf import settings
    from django.core.paginator import Paginator

    return Paginator(queryset, settings.PAGE_SIZE).get_page(request.GET.get("page"))


def _search_term(request: HttpRequest) -> str:
    """Search text from POST (then stored) or the short-lived session value."""
    return (request.session.get(SEARCH_KEY) or "").strip()


@permission_required_code(perms.PATIENT_VIEW)
def patient_list(request: HttpRequest) -> HttpResponse:
    """Patient directory with server-side search and pagination."""
    if request.method == "POST":
        term = (request.POST.get("q") or "").strip()
        if term:
            request.session[SEARCH_KEY] = term
            request.session.modified = True
        else:
            request.session.pop(SEARCH_KEY, None)
        return redirect("patient_list")
    query = _search_term(request)
    queryset = visible_patients(request.user).order_by("-registered_at")
    if query:
        queryset = queryset.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(patient_code__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(
        request,
        "patients/list.html",
        {
            "page": _page(request, queryset),
            "q": query,
            "searched": bool(query),
            "can_register": user_has_permission(
                request.user, perms.PATIENT_CREATE, request=request
            ),
            "can_view_contacts": user_has_permission(
                request.user, perms.PATIENT_VIEW_CONTACT, request=request
            ),
        },
    )


@require_POST
@permission_required_code(perms.PATIENT_VIEW)
def patient_search_clear(request: HttpRequest) -> HttpResponse:
    """Explicitly forget the stored search term."""
    request.session.pop(SEARCH_KEY, None)
    return redirect("patient_list")


@permission_required_code(perms.PATIENT_CREATE)
def patient_add(request: HttpRequest) -> HttpResponse:
    """Register a patient; warn about likely duplicates before committing."""
    form = PatientForm(request.POST or None)
    duplicates: QuerySet[Patient] | None = None
    if request.method == "POST" and form.is_valid():
        if request.POST.get("override") != "1":
            d = find_duplicate_patients(
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                date_of_birth=form.cleaned_data["date_of_birth"],
                phone=form.cleaned_data["phone"],
            )
            duplicates = list(d)[:5]
        if not duplicates:
            patient = create_patient(form=form, user=request.user)
            messages.success(request, f"Patient {patient.patient_code} registered")
            return redirect("patient_detail", pk=patient.pk)
    return render(
        request,
        "patients/form.html",
        {"form": form, "adding": True, "duplicates": duplicates},
    )


@permission_required_code(perms.PATIENT_UPDATE)
def patient_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit demographics; contact management stays on the detail page."""
    patient = get_visible_patient(pk, request.user, request)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        update_patient(patient=patient, form=form, user=request.user)
        messages.success(request, "Patient updated")
        return redirect("patient_detail", pk=patient.pk)
    can_view_contacts = user_has_permission(
        request.user, perms.PATIENT_VIEW_CONTACT, request=request
    )
    return render(
        request,
        "patients/form.html",
        {
            "form": form,
            "patient": patient,
            "adding": False,
            "can_view_contacts": can_view_contacts,
        },
    )


@permission_required_code(perms.PATIENT_VIEW)
def patient_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Demographics, contacts and appointment history; VIEW is audit-logged."""
    patient = get_visible_patient(pk, request.user, request)
    log_patient_view(patient=patient, user=request.user, request=request)
    from apps.appointments.selectors import visible_appointments

    appointment_perms = {
        "book": user_has_permission(
            request.user, perms.APPOINTMENT_CREATE, request=request
        ),
    }
    history = visible_appointments(request.user).filter(patient=patient).order_by(
        "-scheduled_start"
    ).select_related("doctor", "department")[:15]
    return render(
        request,
        "patients/detail.html",
        {
            "patient": patient,
            "phone_display": display_phone(patient, request.user),
            "contacts": patient.contacts.all(),
            "contact_form": EmergencyContactForm(),
            "history": history,
            "can_edit": user_has_permission(
                request.user, perms.PATIENT_UPDATE, request=request
            ),
            "can_view_contacts": user_has_permission(
                request.user, perms.PATIENT_VIEW_CONTACT, request=request
            ),
            "can_archive": user_has_permission(
                request.user, perms.PATIENT_DELETE, request=request
            ),
            "can_book": appointment_perms["book"],
        },
    )


@require_POST
@permission_required_code(perms.PATIENT_UPDATE)
def contact_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Attach an emergency contact to a patient."""
    patient = get_visible_patient(pk, request.user, request)
    form = EmergencyContactForm(request.POST)
    if form.is_valid():
        add_contact(patient=patient, form=form, user=request.user)
        messages.success(request, "Contact added")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect("patient_detail", pk=patient.pk)


@require_POST
@permission_required_code(perms.PATIENT_UPDATE)
def contact_primary(request: HttpRequest, contact_pk: int) -> HttpResponse:
    """Move the primary flag to a different contact."""
    contact = get_object_or_404(EmergencyContact, pk=contact_pk)
    get_visible_patient(contact.patient_id, request.user, request)
    make_contact_primary(contact=contact, user=request.user)
    messages.success(request, "Primary contact updated")
    return redirect("patient_detail", pk=contact.patient_id)


@permission_required_code(perms.PATIENT_DELETE)
def patient_remove(request: HttpRequest, pk: int) -> HttpResponse:
    """Archive a patient (soft delete) with explicit confirmation."""
    patient = get_visible_patient(pk, request.user, request)
    if request.method == "GET":
        return render(request, "patients/delete.html", {"patient": patient})
    archive_patient(patient=patient, user=request.user)
    messages.success(request, f"Patient {patient.patient_code} archived")
    return redirect("patient_list")
