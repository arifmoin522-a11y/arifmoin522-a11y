"""Appointment query helpers: permission-driven visibility, row-level safe."""
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from core import permissions as perms
from core.permissions import user_has_permission

from .constants import ACTIVE_STATUSES, AppointmentStatus
from .models import Appointment


def visible_appointments(user: Any) -> QuerySet[Appointment]:
    """Queryset scoped by permission; view_own users see only their own.

    Users with appointment.view see everything (queue/reception);
    users with appointment.view_own see only their own rows.
    """
    if user_has_permission(user, perms.APPOINTMENT_VIEW):
        return Appointment.objects.all()
    if user_has_permission(user, perms.APPOINTMENT_VIEW_OWN):
        return Appointment.objects.filter(doctor=user)
    return Appointment.objects.none()


def get_visible_appointment(
    pk: int, user: Any, request: HttpRequest | None = None
) -> Appointment:
    """One appointment (select_related) or 404 — enforced on every endpoint."""
    return get_object_or_404(
        visible_appointments(user).select_related(
            "doctor", "doctor__role", "patient", "department"
        ),
        pk=pk,
    )


def ensure_row_access(appointment: Appointment, user: Any) -> None:
    """Re-check row visibility without a 404 (used by action endpoints)."""
    qs = visible_appointments(user).filter(pk=appointment.pk)
    if not qs.exists():
        raise PermissionDenied("You may not access this appointment.")


def upcoming_for_user(user: Any, *, today: Any, limit: int | None = None) -> QuerySet[Appointment]:
    """Active appointments at/after ``today`` for the user's visibility scope."""
    qs = (
        visible_appointments(user)
        .filter(status=AppointmentStatus.SCHEDULED, scheduled_start__gte=today)
        .select_related("doctor", "patient", "department")
        .order_by("scheduled_start")
    )
    return qs[:limit] if limit else qs


def dashboard_counts(user: Any, request: HttpRequest | None = None) -> dict[str, int]:
    """Today's numbers for the dashboard (scoped by the user's visibility)."""
    from django.utils import timezone

    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timezone.timedelta(days=1)
    base = visible_appointments(user).filter(
        scheduled_start__gte=start, scheduled_start__lt=end
    )
    return {
        "today": base.filter(status__in=list(ACTIVE_STATUSES)).count(),
        "checked_in": base.filter(status=AppointmentStatus.CHECKED_IN).count(),
        "waiting": base.filter(
            status__in=list(ACTIVE_STATUSES), scheduled_start__lt=timezone.now()
        ).count(),
        "completed": base.filter(status=AppointmentStatus.COMPLETED).count(),
    }
