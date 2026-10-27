"""Appointment, doctor schedule and leave models.

Constraint strategy (dual layer):
- every overlap rule is enforced by the service layer under
  ``transaction.atomic`` with ``select_for_update`` (works on all backends);
- schedule confinements use DB check/unique constraints.
"""
import datetime
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import QuerySet
from django.utils.functional import cached_property
from django.utils import timezone

from core import permissions as perms
from core.models import BaseModel, next_sequence_value

from apps.accounts.models import Department, User

from .constants import (
    SEQUENCE_APPOINTMENT,
    AppointmentStatus,
    STATUS_META,
    TRANSITIONS,
)


def doctor_capable_check(user: User) -> bool:
    """Doctor-capable users hold appointment.view_own via their role; no role strings."""
    return (
        getattr(user, "role", None) is not None
        and user.role.permissions.filter(code=perms.APPOINTMENT_VIEW_OWN).exists()
    )


def doctor_capable_users() -> QuerySet[User]:
    """Users whose role includes the doctor permission code."""
    return User.objects.filter(
        role__permissions__code=perms.APPOINTMENT_VIEW_OWN
    ).distinct()


def _format_code(prefix: str, value: int) -> str:
    """Human code from the env-driven prefix and zero-padded digit count."""
    return f"{prefix}-{value:0{settings.CODE_SEQUENCE_DIGITS}d}"


class DoctorSchedule(BaseModel):
    """A weekly availability window for one doctor and weekday."""

    doctor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="schedules"
    )
    weekday = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0)],
        help_text="0=Monday … 6=Sunday (ISO weekday index)",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveSmallIntegerField(
        default=settings.APPOINTMENT_SLOT_MINUTES
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["doctor__full_name", "weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="schedule_end_after_start",
            ),
        ]
        indexes = [models.Index(fields=["doctor", "weekday"])]

    def __str__(self) -> str:
        return f"{self.doctor.full_name} weekday {self.weekday} {self.start_time:%H:%M}"

    def clean(self) -> None:
        """Doctor must be schedule-capable; window must be positive."""
        if self.doctor_id is not None and not doctor_capable_check(self.doctor):
            raise ValidationError(
                {"doctor": "Selected user's role cannot consult appointments."}
            )
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be after start time."})

    @property
    def duration_display(self) -> str:
        return f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"


class DoctorLeave(BaseModel):
    """Time off; blocks every acceptable slot within the covered dates."""

    doctor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="leaves")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.doctor.full_name} leave {self.start_date:%Y-%m-%d}–{self.end_date:%Y-%m-%d}"

    def clean(self) -> None:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before start date."})
        if self.doctor_id is not None and not doctor_capable_check(self.doctor):
            raise ValidationError(
                {"doctor": "Selected user's role cannot consult appointments."}
            )


class Appointment(BaseModel):
    """A booked patient consultation slot."""

    appointment_code = models.CharField(max_length=32, unique=True, editable=False)
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="appointments"
    )
    doctor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="appointments"
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="appointments"
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.SCHEDULED,
        db_index=True,
    )
    reason = models.TextField(blank=True)
    cancellation_reason = models.TextField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    queue_number = models.PositiveIntegerField(null=True, blank=True, editable=False)
    rescheduled_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rescheduled_to",
        editable=False,
    )

    class Meta:
        ordering = ["-scheduled_start"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(scheduled_end__gt=models.F("scheduled_start")),
                name="appointment_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["doctor", "scheduled_start"]),
            models.Index(fields=["patient"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.appointment_code} {self.doctor.full_name} {self.scheduled_start:%Y-%m-%d %H:%M}"

    @cached_property
    def status_meta(self) -> dict[str, str]:
        """Badge metadata for templates (icon + label + fill variant)."""
        return STATUS_META.get(self.status, STATUS_META[AppointmentStatus.SCHEDULED])

    def can_transition_to(self, new_status: str) -> bool:
        """Single source for the state machine (services keep this contract)."""
        return new_status in TRANSITIONS.get(self.status, ())

    @property
    def local_date(self) -> datetime.date:
        """Scheduled date in the hospital's local zone (template helper)."""
        return timezone.localdate(self.scheduled_start)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Allocate the unique appointment_code inside the current transaction."""
        if not self.appointment_code:
            value = next_sequence_value(
                SEQUENCE_APPOINTMENT, start=settings.CODE_SEQUENCE_START
            )
            self.appointment_code = _format_code(
                settings.APPOINTMENT_CODE_PREFIX, value
            )
        super().save(*args, **kwargs)
