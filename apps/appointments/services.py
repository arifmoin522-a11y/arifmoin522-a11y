"""Appointment business rules: slots, booking, the status state machine, queue.

Views stay thin; every mutating function here:
- runs inside ``transaction.atomic()``,
- re-validates data (never trusts the UI),
- writes an ``AuditLog`` entry, and
- raises small, human-readable exceptions callers map to messages.

Slot allocation is serialized through the appointment code sequence row, so
two receptionists racing for the same slot get exactly one success.
"""
import datetime
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Max, QuerySet
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.utils import log_to_audit

from .constants import ACTIVE_STATUSES, AppointmentStatus, TRANSITIONS
from .models import Appointment, DoctorLeave, DoctorSchedule
from core.models import next_sequence_value

WAITING_STATUSES: tuple[str, ...] = (AppointmentStatus.CHECKED_IN,)


class AppointmentError(Exception):
    """User-facing validation failure (the message is safe to display)."""


class StateTransitionError(AppointmentError):
    """The current status forbids the requested change."""


class SlotUnavailableError(AppointmentError):
    """The doctor/patient window is taken or the doctor is unavailable."""


@dataclass(frozen=True)
class BookedSlot:
    """A concrete bookable instant (slot start == appointment start)."""

    doctor: Any
    date: datetime.date
    start: datetime.datetime
    end: datetime.datetime


# ---------------------------------------------------------------- lookups
def _active_appointments() -> QuerySet[Appointment]:
    """Appointments that currently occupy a calendar slot."""
    return Appointment.objects.filter(
        status__in=list(ACTIVE_STATUSES)
    )


def _local_day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """[00:00, next 00:00) for ``day`` in the local timezone."""
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min),
        timezone.get_current_timezone(),
    )
    return start, start + datetime.timedelta(days=1)


def doctor_schedule_for(doctor: Any, day: datetime.date) -> DoctorSchedule | None:
    """The active weekly schedule row covering ``day``."""
    return (
        DoctorSchedule.objects.filter(
            doctor=doctor, weekday=day.weekday(), is_active=True
        )
        .order_by("pk")
        .first()
    )


# ----------------------------------------------------------------- slots
def get_available_slots(doctor: Any, day: datetime.date) -> list[BookedSlot]:
    """Slot grid = schedule window − leave − existing bookings − past times."""
    schedule = doctor_schedule_for(doctor, day)
    if schedule is None:
        return []
    if DoctorLeave.objects.filter(
        doctor=doctor, start_date__lte=day, end_date__gte=day
    ).exists():
        return []

    day_start, day_end = _local_day_bounds(day)
    taken = list(
        _active_appointments()
        .filter(
            doctor=doctor,
            scheduled_start__gte=day_start,
            scheduled_start__lt=day_end,
        )
        .values_list("scheduled_start", "scheduled_end")
    )
    step = datetime.timedelta(
        minutes=schedule.slot_minutes or settings.APPOINTMENT_SLOT_MINUTES
    )
    local_tz = timezone.get_current_timezone()
    cursor = timezone.make_aware(
        datetime.datetime.combine(day, schedule.start_time), local_tz
    )
    window_end = timezone.make_aware(
        datetime.datetime.combine(day, schedule.end_time), local_tz
    )
    now = timezone.now()
    slots: list[BookedSlot] = []
    while cursor + step <= window_end:
        slot_end = cursor + step
        if cursor > now and not any(
            existing_start < slot_end and cursor < existing_end
            for existing_start, existing_end in taken
        ):
            slots.append(BookedSlot(doctor=doctor, date=day, start=cursor, end=slot_end))
        cursor += step
    return slots


# --------------------------------------------------------- internal checks
def _matching_slot(doctor: Any, start: datetime.datetime) -> BookedSlot:
    """The exact offered slot starting at ``start`` or a clear error."""
    slots = get_available_slots(doctor, start.date())
    for slot in slots:
        if slot.start == start:
            return slot
    raise SlotUnavailableError(
        "That exact time is not an offered slot for this doctor — please pick "
        "one of the available times."
    )


def _patient_double_booked(
    patient: Any, start: datetime.datetime, end: datetime.datetime
) -> bool:
    """Patient overlap check across ALL doctors for active appointments."""
    return _active_appointments().filter(
        patient_id=patient.pk, scheduled_start__lt=end, scheduled_end__gt=start
    ).exists()


# ---------------------------------------------------------------- booking
def book_appointment(
    *,
    patient: Any,
    doctor: Any,
    start: datetime.datetime,
    department: Any | None = None,
    reason: str = "",
    actor: Any = None,
    request: Any = None,
) -> Appointment:
    """Create one appointment; allocation is serialized and audited.

    The slot must be an exact offered slot, free for the doctor AND the
    patient. Concurrency: the code-sequence row lock serialises running
    bookings, so exactly one of two racing bookings succeeds.
    """
    if timezone.is_naive(start):
        start = timezone.make_aware(start, timezone.get_current_timezone())
    with transaction.atomic():
        # Serialise bookings: everyone takes the next code under row lock.
        code_value = next_sequence_value("appointment_code", start=settings.CODE_SEQUENCE_START)
        slot = _matching_slot(doctor, start)
        if _patient_double_booked(patient, slot.start, slot.end):
            raise SlotUnavailableError(
                f"{patient.full_name or 'This patient'} already has an "
                "appointment around that time. Choose another slot."
            )
        appointment = Appointment(
            patient=patient,
            doctor=doctor,
            department=department,
            scheduled_start=slot.start,
            scheduled_end=slot.end,
            status=AppointmentStatus.SCHEDULED,
            reason=reason,
            created_by=actor,
            appointment_code=_code(settings.APPOINTMENT_CODE_PREFIX, code_value),
        )
        appointment.full_clean()
        appointment.save()
        log_to_audit(
            user=actor,
            action=AuditLog.Action.CREATE,
            request=request,
            object_type="appointment",
            object_id=appointment.appointment_code,
            details=f"Booked {appointment.patient.patient_code} with "
            f"{doctor.full_name} at {slot.start:%Y-%m-%d %H:%M}",
        )
    return appointment


def _code(prefix: str, value: int) -> str:
    """Human code from env-driven prefix and zero-padded digit count."""
    return f"{prefix}-{value:0{settings.CODE_SEQUENCE_DIGITS}d}"


def _locked(pk: int) -> Appointment:
    """Row-locked appointment for state changes (must be in a transaction)."""
    return Appointment.objects.select_for_update().get(pk=pk)


def _set_status(
    appointment: Appointment,
    new_status: str,
    *,
    actor: Any,
    request: Any = None,
    details: str = "",
    update_fields: list[str] | None = None,
) -> None:
    """Apply the single state machine + write the audit entry.

    ``update_fields`` must include ``"status"``; extra fields the caller has
    already set on the instance are saved together with it.
    """
    old_status = appointment.status
    if not appointment.can_transition_to(new_status):
        valid = TRANSITIONS.get(old_status, ())
        labels = [AppointmentStatus(value).label for value in valid]
        options = ", ".join(labels) if labels else "nothing (terminal)"
        raise StateTransitionError(
            f"An appointment that is “{appointment.get_status_display()}” can "
            f"only move to: {options}."
        )
    appointment.status = new_status
    appointment.save(update_fields=update_fields or ["status"])
    log_to_audit(
        user=actor,
        action=AuditLog.Action.UPDATE,
        request=request,
        object_type="appointment",
        object_id=appointment.appointment_code,
        details=f"Status {old_status} -> {new_status}"
        + (f" — {details}" if details else ""),
    )


def _transition_guard_window(start: datetime.datetime) -> None:
    """Cancellation cannot happen inside the configured pre-start window."""
    window = settings.APPOINTMENT_CANCELLATION_WINDOW_MINUTES
    if window <= 0:
        return
    limit = start - datetime.timedelta(minutes=window)
    if timezone.now() > limit:
        raise AppointmentError(
            f"This appointment starts within {window} minutes, so it can no "
            "longer be cancelled from the front desk."
        )


# ------------------------------------------------------------- operations
def cancel_appointment(
    *,
    appointment: Appointment,
    actor: Any,
    reason: str,
    request: Any = None,
) -> Appointment:
    """SCHEDULED/CHECKED_IN -> CANCELLED with a mandatory reason."""
    if not reason or not reason.strip():
        raise AppointmentError("Please give a reason for cancelling.")
    with transaction.atomic():
        locked = _locked(appointment.pk)
        if locked.scheduled_start > timezone.now():
            _transition_guard_window(locked.scheduled_start)
        locked.cancellation_reason = reason.strip()
        _set_status(
            locked,
            AppointmentStatus.CANCELLED,
            actor=actor,
            request=request,
            details=f"reason: {reason.strip()}",
            update_fields=["status", "cancellation_reason"],
        )
    return locked


def mark_no_show(
    *, appointment: Appointment, actor: Any, request: Any = None
) -> Appointment:
    """SCHEDULED -> NO_SHOW (typically recorded after the start passed)."""
    with transaction.atomic():
        locked = _locked(appointment.pk)
        _set_status(
            locked,
            AppointmentStatus.NO_SHOW,
            actor=actor,
            request=request,
            details="Patient did not arrive",
        )
    return locked


def check_in(
    *, appointment: Appointment, actor: Any, request: Any = None
) -> Appointment:
    """SCHEDULED -> CHECKED_IN; assigns the doctor/day queue number."""
    with transaction.atomic():
        locked = _locked(appointment.pk)
        day_start, day_end = _local_day_bounds(
            timezone.localdate(locked.scheduled_start)
        )
        last_number = (
            Appointment.objects.filter(
                doctor=locked.doctor,
                scheduled_start__gte=day_start,
                scheduled_start__lt=day_end,
                queue_number__isnull=False,
            )
            .aggregate(last=Max("queue_number"))
            .get("last")
            or 0
        )
        locked.checked_in_at = timezone.now()
        locked.queue_number = int(last_number) + 1
        _set_status(
            locked,
            AppointmentStatus.CHECKED_IN,
            actor=actor,
            request=request,
            details=f"queue {locked.queue_number}",
            update_fields=["status", "checked_in_at", "queue_number"],
        )
    return locked


def start_visit(
    *, appointment: Appointment, actor: Any, request: Any = None
) -> Appointment:
    """CHECKED_IN -> IN_PROGRESS."""
    with transaction.atomic():
        locked = _locked(appointment.pk)
        _set_status(
            locked,
            AppointmentStatus.IN_PROGRESS,
            actor=actor,
            request=request,
        )
    return locked


def complete_visit(
    *, appointment: Appointment, actor: Any, request: Any = None
) -> Appointment:
    """IN_PROGRESS -> COMPLETED."""
    with transaction.atomic():
        locked = _locked(appointment.pk)
        _set_status(
            locked,
            AppointmentStatus.COMPLETED,
            actor=actor,
            request=request,
        )
    return locked


def reschedule_appointment(
    *,
    appointment: Appointment,
    actor: Any,
    new_doctor: Any,
    new_start: datetime.datetime,
    reason: str,
    request: Any = None,
) -> Appointment:
    """Cancel the old record and book a new linked one (history preserved)."""
    if not reason or not reason.strip():
        raise AppointmentError("Please give a reason for rescheduling.")
    with transaction.atomic():
        locked = _locked(appointment.pk)
        locked.cancellation_reason = f"Rescheduled — {reason.strip()}"
        _set_status(
            locked,
            AppointmentStatus.CANCELLED,
            actor=actor,
            request=request,
            details=f"reason: rescheduled — {reason.strip()}",
            update_fields=["status", "cancellation_reason"],
        )
        new_appointment = _book_linked(
            old=locked,
            actor=actor,
            request=request,
            new_doctor=new_doctor,
            new_start=new_start,
            reason=reason.strip(),
        )
    return new_appointment


def _book_linked(
    *,
    old: Appointment,
    actor: Any,
    request: Any,
    new_doctor: Any,
    new_start: datetime.datetime,
    reason: str,
) -> Appointment:
    """Create the follow-up record linked back to the cancelled original."""
    new_start = (
        timezone.make_aware(new_start, timezone.get_current_timezone())
        if timezone.is_naive(new_start)
        else new_start
    )
    code_value = next_sequence_value(
        "appointment_code", start=settings.CODE_SEQUENCE_START
    )
    slot = _matching_slot(new_doctor, new_start)
    if _patient_double_booked(old.patient, slot.start, slot.end):
        raise SlotUnavailableError(
            "This patient already has an appointment around that time. "
            "Choose another slot."
        )
    new_appointment = Appointment(
        patient=old.patient,
        doctor=new_doctor,
        department=old.department,
        scheduled_start=slot.start,
        scheduled_end=slot.end,
        status=AppointmentStatus.SCHEDULED,
        reason=old.reason or reason,
        created_by=actor,
        rescheduled_from=old,
    )
    new_appointment.appointment_code = _code(
        settings.APPOINTMENT_CODE_PREFIX, code_value
    )
    new_appointment.full_clean()
    new_appointment.save()
    log_to_audit(
        user=actor,
        action=AuditLog.Action.CREATE,
        request=request,
        object_type="appointment",
        object_id=new_appointment.appointment_code,
        details=f"Rescheduled from {old.appointment_code} to "
        f"{slot.start:%Y-%m-%d %H:%M}",
    )
    return new_appointment
