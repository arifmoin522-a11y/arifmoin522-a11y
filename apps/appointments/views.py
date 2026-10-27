"""Appointment views: book flow, queue, doctor own view, week grid, actions.

Every endpoint binds permission codes from ``core.permissions``; state
changes are POST-only; row-level access is enforced on each fetch.
"""
import datetime
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.db.models import Q, QuerySet
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from core import permissions as perms
from core.decorators import permission_required_any, permission_required_code
from core.permissions import user_has_permission

from .constants import ACTIVE_STATUSES, AppointmentStatus
from .forms import (
    BookConfirmForm,
    CancelForm,
    DoctorLeaveForm,
    DoctorScheduleForm,
    RescheduleForm,
)
from .models import Appointment, DoctorLeave, DoctorSchedule, doctor_capable_users
from .selectors import get_visible_appointment, visible_appointments
from .services import (
    AppointmentError,
    book_appointment,
    cancel_appointment,
    check_in,
    complete_visit,
    get_available_slots,
    mark_no_show,
    reschedule_appointment,
    start_visit,
)

DATE_FMT = "%Y-%m-%d"
SLOT_FMT = "%H%M"


def _parse_date(raw: str | None) -> datetime.date | None:
    """Parse a YYYY-MM-DD GET value; noisy input simply selects today."""
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, DATE_FMT).date()
    except ValueError:
        return None


def _page(request: HttpRequest, queryset: QuerySet[Appointment]) -> Any:
    """Pagination honouring the env-driven page size."""
    from django.conf import settings
    from django.core.paginator import Paginator

    return Paginator(queryset, settings.PAGE_SIZE).get_page(request.GET.get("page"))


def _day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), timezone.get_current_timezone()
    )
    return start, start + datetime.timedelta(days=1)


# ------------------------------------------------------------- row helper
def _allowed_actions(appt: Appointment, user: Any, request: HttpRequest) -> dict[str, bool]:
    """Which action buttons the current user/state combination allows."""
    may_cancel = user_has_permission(user, perms.APPOINTMENT_CANCEL, request)
    may_checkin = user_has_permission(user, perms.APPOINTMENT_CHECKIN, request)
    may_reschedule = user_has_permission(user, perms.APPOINTMENT_RESCHEDULE, request)
    return {
        "checkin": may_checkin and appt.can_transition_to(AppointmentStatus.CHECKED_IN),
        "start": may_checkin and appt.can_transition_to(AppointmentStatus.IN_PROGRESS),
        "complete": may_checkin and appt.can_transition_to(AppointmentStatus.COMPLETED),
        "no_show": may_cancel and appt.can_transition_to(AppointmentStatus.NO_SHOW),
        "cancel": may_cancel and appt.can_transition_to(AppointmentStatus.CANCELLED),
        "reschedule": may_reschedule and appt.can_transition_to(AppointmentStatus.CANCELLED),
    }


def _rows(appointments: Any, user: Any, request: HttpRequest) -> list[dict]:
    """Template rows: appointment + status-driven actions."""
    return [
        {"appt": appt, "actions": _allowed_actions(appt, user, request)}
        for appt in appointments
    ]


def _desk_counts(
    user: Any, day: datetime.date, request: HttpRequest
) -> dict[str, int]:
    """Headline numbers for a queue day (scoped by the user's visibility)."""
    start, end = _day_bounds(day)
    base = visible_appointments(user).filter(
        scheduled_start__gte=start, scheduled_start__lt=end
    )
    return {
        "total": base.filter(status__in=list(ACTIVE_STATUSES)).count(),
        "checked_in": base.filter(status=AppointmentStatus.CHECKED_IN).count(),
        "waiting": base.filter(
            status__in=list(ACTIVE_STATUSES),
            scheduled_start__lt=_judge_now(),
        ).count(),
        "completed": base.filter(status=AppointmentStatus.COMPLETED).count(),
    }


def _judge_now() -> datetime.datetime:
    """One place for "now" so tests and timezones stay consistent."""
    return timezone.now()


# ------------------------------------------------------------------ lists
@permission_required_any(perms.APPOINTMENT_VIEW, perms.APPOINTMENT_VIEW_OWN)
def appointment_list(request: HttpRequest) -> HttpResponse:
    """Today's queue (full visibility) or "My appointments today" (view_own)."""
    user = request.user
    full_view = user_has_permission(user, perms.APPOINTMENT_VIEW, request)
    day = _parse_date(request.GET.get("date")) or timezone.localdate()
    start, end = _day_bounds(day)
    queryset = (
        visible_appointments(user)
        .select_related("doctor", "patient", "department", "doctor__role")
        .filter(scheduled_start__gte=start, scheduled_start__lt=end)
        .order_by("scheduled_start")
    )
    doctors = doctor_capable_users().order_by("full_name") if full_view else None
    doctor_id = request.GET.get("doctor")
    if full_view and doctor_id:
        try:
            queryset = queryset.filter(doctor__pk=int(doctor_id))
        except ValueError:
            queryset = queryset.filter(doctor__pk=0)
    context = {
        "page": _page(request, queryset) if full_view else None,
        "rows": _rows(queryset if full_view else queryset[:50], user, request),
        "day": day,
        "prev_day": day - datetime.timedelta(days=1),
        "next_day": day + datetime.timedelta(days=1),
        "doctors": doctors,
        "doctor_id": doctor_id or "",
        "full_view": full_view,
        "counts": _desk_counts(user, day, request),
        "today": timezone.localdate(),
    }
    if not full_view:
        upcoming = (
            visible_appointments(user)
            .select_related("doctor", "patient", "department")
            .filter(status=AppointmentStatus.SCHEDULED, scheduled_start__gte=end)
            .order_by("scheduled_start")[:10]
        )
        context["upcoming_rows"] = _rows(upcoming, user, request)
    return render(request, "appointments/list.html", context)


@permission_required_any(perms.APPOINTMENT_VIEW, perms.APPOINTMENT_VIEW_OWN)
def week_calendar(request: HttpRequest) -> HttpResponse:
    """Simple server-rendered week grid per doctor (no JS libraries)."""
    user = request.user
    full_view = user_has_permission(user, perms.APPOINTMENT_VIEW, request)
    requested = _parse_date(request.GET.get("week")) or timezone.localdate()
    monday = requested - datetime.timedelta(days=requested.weekday())
    week = [monday + datetime.timedelta(days=i) for i in range(7)]
    doctors = list(doctor_capable_users()) if full_view else [user]
    grid: list[dict] = []
    for doctor in doctors:
        cells = []
        for day in week:
            start, end = _day_bounds(day)
            appts = list(
                visible_appointments(user)
                .filter(
                    doctor=doctor,
                    scheduled_start__gte=start,
                    scheduled_start__lt=end,
                )
                .select_related("patient", "department")
                .order_by("scheduled_start")
            )
            cells.append({"day": day, "appts": appts})
        grid.append({"doctor": doctor, "cells": cells})
    return render(
        request,
        "appointments/week.html",
        {
            "grid": grid,
            "week": week,
            "prev_week": monday - datetime.timedelta(days=7),
            "next_week": monday + datetime.timedelta(days=7),
            "full_view": full_view,
        },
    )


# ----------------------------------------------------------------- booking
@permission_required_code(perms.APPOINTMENT_CREATE)
def appointment_book(request: HttpRequest) -> HttpResponse:
    """Four-step flow: patient -> doctor -> date -> slot -> confirm."""
    if request.method == "POST" and request.POST.get("action") == "search":
        term = (request.POST.get("patient_q") or "").strip()
        request.session["book_patient_q"] = term
        return redirect("appointment_book")
    from apps.patients.selectors import visible_patients

    patient_q = (request.session.get("book_patient_q") or "").strip()
    patient = _optionally_fetch(request, "patient", visible_patients(request.user))
    doctor = _optionally_fetch(request, "doctor", doctor_capable_users())
    day = _parse_date(request.GET.get("date"))
    slot_raw = (request.GET.get("slot") or "").strip()

    if request.method == "POST" and patient is not None and doctor is not None and slot_raw:
        form = BookConfirmForm(request.POST)
        try:
            slot_start = datetime.datetime.strptime(
                f"{(day or timezone.localdate()).isoformat()}-{slot_raw}",
                f"{DATE_FMT}-%H%M",
            )
        except ValueError:
            slot_start = None
        if slot_start is None:
            messages.error(request, "Pick a valid time slot.")
            return redirect("appointment_book")
        if form.is_valid():
            try:
                appointment = book_appointment(
                    patient=patient,
                    doctor=doctor,
                    start=slot_start,
                    department=form.cleaned_data["department"],
                    reason=form.cleaned_data["reason"],
                    actor=request.user,
                    request=request,
                )
            except AppointmentError as error:
                messages.error(request, str(error))
            else:
                messages.success(
                    request, f"Appointment {appointment.appointment_code} booked"
                )
                request.session.pop("book_patient_q", None)
                return redirect("appointment_detail", pk=appointment.pk)
        flow_day = day or timezone.localdate()
        slot_start_aware = timezone.make_aware(
            slot_start, timezone.get_current_timezone()
        )
        return render(
            request,
            "appointments/book.html",
            {
                "step": "confirm",
                "form": form,
                "patient": patient,
                "doctor": doctor,
                "day": flow_day,
                "slot_time": slot_start_aware,
                "slot_raw": slot_raw,
            },
        )

    # ---- progressive steps rendered by one flow template
    step = "patient"
    if patient is not None:
        step = "doctor"
    if patient is not None and doctor is not None:
        step = "date"
    if patient is not None and doctor is not None and day is not None:
        step = "slot" if not slot_raw else "confirm"

    context: dict[str, Any] = {"step": step, "patient": patient, "doctor": doctor}
    if step == "patient":
        matches = visible_patients(request.user).order_by("first_name")[:15]
        if patient_q:
            matches = matches.filter(
                Q(first_name__icontains=patient_q)
                | Q(last_name__icontains=patient_q)
                | Q(patient_code__icontains=patient_q)
                | Q(phone__icontains=patient_q)
            )
        context.update({"patient_q": patient_q, "patient_matches": list(matches)})
    elif step == "doctor":
        context["doctors"] = list(doctor_capable_users().order_by("full_name"))
    elif step == "date":
        context["min_date"] = timezone.localdate()
    elif step == "slot":
        context["slots"] = get_available_slots(doctor, day or timezone.localdate())
        context["day"] = day
        if not context["slots"]:
            context["no_slots"] = True
    elif step == "confirm":
        slot_start = datetime.datetime.strptime(
            f"{day.isoformat()}-{slot_raw}", f"{DATE_FMT}-%H%M"
        )
        context.update(
            {
                "form": BookConfirmForm(),
                "day": day,
                "slot_time": timezone.make_aware(slot_start, timezone.get_current_timezone()),
                "slot_raw": slot_raw,
            }
        )
    return render(request, "appointments/book.html", context)


def _optionally_fetch(request: HttpRequest, param: str, queryset: QuerySet) -> Any:
    """GET value -> row or None; invalid ids never blow up the flow."""
    raw = request.GET.get(param)
    if not raw:
        return None
    try:
        return queryset.get(pk=int(raw))
    except (ValueError, queryset.model.DoesNotExist):
        return None


# ----------------------------------------------------------------- detail
@permission_required_any(perms.APPOINTMENT_VIEW, perms.APPOINTMENT_VIEW_OWN)
def appointment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Single appointment with contextual action modals."""
    appt = get_visible_appointment(pk, request.user, request)
    logs = (
        AuditLog.objects.filter(object_type="appointment", object_id=appt.appointment_code)
        .select_related("user")
        .order_by("-timestamp")[:8]
    )
    return render(
        request,
        "appointments/detail.html",
        {
            "appt": appt,
            "actions": _allowed_actions(appt, request.user, request),
            "cancel_form": CancelForm(),
            "reschedule_form": RescheduleForm(),
            "logs": logs,
        },
    )


def _handle_appointment_error(
    request: HttpRequest, error: AppointmentError, pk: int
) -> HttpResponse:
    messages.error(request, str(error))
    return redirect("appointment_detail", pk=pk)


@require_POST
@permission_required_code(perms.APPOINTMENT_CHECKIN)
def appointment_checkin(request: HttpRequest, pk: int) -> HttpResponse:
    """Check the patient in and queue them for the doctor."""
    appt = get_visible_appointment(pk, request.user, request)
    try:
        updated = check_in(appointment=appt, actor=request.user, request=request)
    except AppointmentError as error:
        return _handle_appointment_error(request, error, pk)
    messages.success(
        request, f"Checked in — queue number {updated.queue_number}"
    )
    return redirect("appointment_detail", pk=pk)


@require_POST
@permission_required_code(perms.APPOINTMENT_CHECKIN)
def appointment_start(request: HttpRequest, pk: int) -> HttpResponse:
    """Move a checked-in appointment to IN_PROGRESS."""
    appt = get_visible_appointment(pk, request.user, request)
    try:
        start_visit(appointment=appt, actor=request.user, request=request)
    except AppointmentError as error:
        return _handle_appointment_error(request, error, pk)
    messages.success(request, "Visit started")
    return redirect("appointment_detail", pk=pk)


@require_POST
@permission_required_code(perms.APPOINTMENT_CHECKIN)
def appointment_complete(request: HttpRequest, pk: int) -> HttpResponse:
    """Move an in-progress visit to COMPLETED."""
    appt = get_visible_appointment(pk, request.user, request)
    try:
        complete_visit(appointment=appt, actor=request.user, request=request)
    except AppointmentError as error:
        return _handle_appointment_error(request, error, pk)
    messages.success(request, "Visit completed")
    return redirect("appointment_detail", pk=pk)


@require_POST
@permission_required_code(perms.APPOINTMENT_CANCEL)
def appointment_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """Cancel with a mandatory reason (modal in the detail page)."""
    appt = get_visible_appointment(pk, request.user, request)
    form = CancelForm(request.POST)
    if form.is_valid():
        try:
            cancel_appointment(
                appointment=appt,
                actor=request.user,
                reason=form.cleaned_data["reason"],
                request=request,
            )
        except AppointmentError as error:
            return _handle_appointment_error(request, error, pk)
        messages.success(request, "Appointment cancelled")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect("appointment_detail", pk=pk)


@require_POST
@permission_required_code(perms.APPOINTMENT_CANCEL)
def appointment_no_show(request: HttpRequest, pk: int) -> HttpResponse:
    """Record that the patient never arrived."""
    appt = get_visible_appointment(pk, request.user, request)
    try:
        mark_no_show(appointment=appt, actor=request.user, request=request)
    except AppointmentError as error:
        return _handle_appointment_error(request, error, pk)
    messages.success(request, "Marked as no-show")
    return redirect("appointment_detail", pk=pk)


@permission_required_code(perms.APPOINTMENT_RESCHEDULE)
def appointment_reschedule(request: HttpRequest, pk: int) -> HttpResponse:
    """Two-step reschedule: reasons/doctor/date, then the new slot.

    The service cancels the old record and books a new linked one.
    """
    appt = get_visible_appointment(pk, request.user, request)
    if request.method != "POST":
        return render(
            request,
            "appointments/reschedule.html",
            {"form": RescheduleForm(), "appt": appt},
        )
    action = request.POST.get("action") or "pick"
    form = RescheduleForm(request.POST)
    if action == "confirm":
        slot_raw = (request.POST.get("slot") or "").strip()
        if form.is_valid():
            try:
                slot_start = datetime.datetime.strptime(
                    f"{form.cleaned_data['date'].isoformat()}-{slot_raw}",
                    f"{DATE_FMT}-%H%M",
                )
                reschedule_appointment(
                    appointment=appt,
                    actor=request.user,
                    new_doctor=form.cleaned_data["doctor"],
                    new_start=slot_start,
                    reason=form.cleaned_data["reason"],
                    request=request,
                )
            except (ValueError, AppointmentError) as error:
                messages.error(
                    request,
                    str(error)
                    if isinstance(error, AppointmentError)
                    else "Pick a valid time slot.",
                )
                return redirect("appointment_reschedule", pk=pk)
            messages.success(request, "Appointment rescheduled")
            return redirect("appointment_detail", pk=appt.pk)
    if not form.is_valid():
        return render(
            request, "appointments/reschedule.html", {"form": form, "appt": appt}
        )
    doctor = form.cleaned_data["doctor"]
    date = form.cleaned_data["date"]
    slots = get_available_slots(doctor, date)
    return render(
        request,
        "appointments/reschedule.html",
        {
            "form": form,
            "appt": appt,
            "slots": slots,
            "day": date,
            "reschedule_doctor": doctor,
        },
    )


# -------------------------------------------------------------- schedules
def _schedule_context(request: HttpRequest) -> dict[str, Any]:
    schedules = (
        DoctorSchedule.objects.select_related("doctor", "doctor__role")
        .order_by("doctor__full_name", "weekday", "start_time")
    )
    leaves = (
        DoctorLeave.objects.select_related("doctor").order_by("-start_date")[:20]
    )
    can_manage = user_has_permission(
        request.user, perms.SCHEDULE_MANAGE, request
    )
    return {
        "schedules": schedules,
        "leaves": leaves,
        "can_manage": can_manage,
    }


@permission_required_code(perms.SCHEDULE_VIEW)
def schedule_list(request: HttpRequest) -> HttpResponse:
    """Doctor weekly schedules plus recent leave windows."""
    return render(request, "appointments/schedule_list.html", _schedule_context(request))


@permission_required_code(perms.SCHEDULE_MANAGE)
def schedule_add(request: HttpRequest) -> HttpResponse:
    form = DoctorScheduleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        schedule = form.save(commit=False)
        schedule.created_by = request.user
        schedule.save()
        messages.success(request, "Schedule saved")
        return redirect("schedule_list")
    return render(
        request, "appointments/schedule_form.html", {"form": form, "adding": True}
    )


@permission_required_code(perms.SCHEDULE_MANAGE)
def schedule_edit(request: HttpRequest, pk: int) -> HttpResponse:
    schedule = DoctorSchedule.objects.get(pk=pk)
    form = DoctorScheduleForm(request.POST or None, instance=schedule)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Schedule updated")
        return redirect("schedule_list")
    return render(
        request,
        "appointments/schedule_form.html",
        {"form": form, "schedule": schedule, "adding": False},
    )


@require_POST
@permission_required_code(perms.SCHEDULE_MANAGE)
def schedule_remove(request: HttpRequest, pk: int) -> HttpResponse:
    """Soft-delete the schedule row."""
    schedule = DoctorSchedule.objects.get(pk=pk)
    schedule.soft_delete(user=request.user)
    messages.success(request, "Schedule removed")
    return redirect("schedule_list")


@permission_required_code(perms.SCHEDULE_MANAGE)
def leave_add(request: HttpRequest) -> HttpResponse:
    form = DoctorLeaveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        leave = form.save(commit=False)
        leave.created_by = request.user
        leave.save()
        messages.success(request, "Leave recorded")
        return redirect("schedule_list")
    return render(request, "appointments/leave_form.html", {"form": form})


@require_POST
@permission_required_code(perms.SCHEDULE_MANAGE)
def leave_remove(request: HttpRequest, pk: int) -> HttpResponse:
    leave = DoctorLeave.objects.get(pk=pk)
    leave.soft_delete(user=request.user)
    messages.success(request, "Leave removed")
    return redirect("schedule_list")
