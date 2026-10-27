"""Appointments phase constants: statuses, transitions and display metadata.

Rule 11: adding a status or changing the allowed transitions is a change to
THIS FILE ONLY. Views and templates read the TextChoices/TRANSITIONS/
STATUS_META definitions here and never spell status strings.
"""
from django.db import models


class AppointmentStatus(models.TextChoices):
    """Lifecycle of an appointment."""

    SCHEDULED = "SCHEDULED", "Scheduled"
    CHECKED_IN = "CHECKED_IN", "Checked in"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No show"


#: values of AppointmentStatus that occupy a doctor's/patient's calendar
ACTIVE_STATUSES: tuple[str, ...] = (
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CHECKED_IN,
    AppointmentStatus.IN_PROGRESS,
)

#: status -> statuses it may legally move to; one dictionary, read by services
TRANSITIONS: dict[str, tuple[str, ...]] = {
    AppointmentStatus.SCHEDULED: (
        AppointmentStatus.CHECKED_IN,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    ),
    AppointmentStatus.CHECKED_IN: (
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.CANCELLED,
    ),
    AppointmentStatus.IN_PROGRESS: (AppointmentStatus.COMPLETED,),
    AppointmentStatus.COMPLETED: (),
    AppointmentStatus.CANCELLED: (),
    AppointmentStatus.NO_SHOW: (),
}

#: status -> how templates render it. variant maps to the monochrome badge
#: styles (done=filled check, pending=outlined arrow, urgent=filled alert);
#: icon is an SVG sprite symbol id. Every status has a distinct icon+label,
#: so state never depends on colour alone.
STATUS_META: dict[str, dict[str, str]] = {
    AppointmentStatus.SCHEDULED: {
        "variant": "pending", "icon": "calendar",
    },
    AppointmentStatus.CHECKED_IN: {
        "variant": "pending", "icon": "check",
    },
    AppointmentStatus.IN_PROGRESS: {
        "variant": "pending", "icon": "arrow_forward",
    },
    AppointmentStatus.COMPLETED: {
        "variant": "done", "icon": "check",
    },
    AppointmentStatus.CANCELLED: {
        "variant": "urgent", "icon": "alert",
    },
    AppointmentStatus.NO_SHOW: {
        "variant": "urgent", "icon": "alert",
    },
}

#: name used as the CodeSequence key for appointment codes (never changed)
SEQUENCE_APPOINTMENT = "appointment_code"
