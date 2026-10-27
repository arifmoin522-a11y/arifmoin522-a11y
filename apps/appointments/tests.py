"""Appointment front-desk tests: slots, state machine, permissions.

Run with: python manage.py test apps.appointments
"""
import datetime

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission, Role
from apps.appointments.constants import AppointmentStatus
from apps.appointments.models import Appointment, DoctorLeave, DoctorSchedule
from apps.appointments.services import (
    AppointmentError,
    SlotUnavailableError,
    book_appointment,
    cancel_appointment,
    check_in,
    complete_visit,
    get_available_slots,
    mark_no_show,
    reschedule_appointment,
    start_visit,
)
from apps.patients.constants import Gender
from apps.patients.models import Patient
from core import permissions as perms

from apps.accounts.tests import make_user


def make_role_with(role_name: str, codes: list[str]) -> Role:
    role = Role.objects.create(name=role_name)
    for code in codes:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"description": code}
        )
        role.permissions.add(permission)
    return role


def make_future_day() -> datetime.date:
    """First date at least 3h ahead whose weekday is inside the work week."""
    candidate = timezone.localdate()
    for _ in range(7):
        start_naive = datetime.datetime.combine(candidate, datetime.time(9, 0))
        start = timezone.make_aware(start_naive, timezone.get_current_timezone())
        if start > timezone.now() + timezone.timedelta(hours=3):
            return candidate
        candidate += datetime.timedelta(days=1)
    raise AssertionError("no future workday found within a week")


def make_patient(name: str) -> Patient:
    """A barebones fake patient for appointment tests."""
    return Patient.objects.create(
        first_name=name,
        last_name="Tester",
        date_of_birth=datetime.date(1988, 8, 8),
        gender=Gender.OTHER,
        phone="01122-334455",
    )


def _ensure_schedule(doctor: object, day: datetime.date, first_hour=9, last_hour=11):
    DoctorSchedule.objects.get_or_create(
        doctor=doctor,
        weekday=day.weekday(),
        start_time=datetime.time(first_hour, 0),
        defaults={
            "end_time": datetime.time(last_hour, 0),
            "slot_minutes": 30,
        },
    )


def slot(day: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    naive = datetime.datetime.combine(day, datetime.time(hour, minute))
    return timezone.make_aware(naive, timezone.get_current_timezone())


class SlotTests(TestCase):
    """Slot fitting: schedule, leave, conflicts and booking."""

    def setUp(self) -> None:
        self.doctor = make_user(
            "slot.doctor@example.test",
            role=make_role_with("Slot Doctor (t)", [perms.APPOINTMENT_VIEW_OWN]),
        )
        self.other_doctor = make_user(
            "slot.doctor2@example.test",
            role=make_role_with("Slot Doctor 2 (t)", [perms.APPOINTMENT_VIEW_OWN]),
        )
        self.day = make_future_day()
        for user in (self.doctor, self.other_doctor):
            _ensure_schedule(user, self.day)
        self.patient_a = make_patient("Alpha")
        self.patient_b = make_patient("Beta")

    def test_book_creates_code_and_default_status(self) -> None:
        appt = book_appointment(
            patient=self.patient_a, doctor=self.doctor, start=slot(self.day, 9)
        )
        self.assertTrue(appt.appointment_code.startswith("APT-"))
        self.assertEqual(appt.status, AppointmentStatus.SCHEDULED)

    def test_doctor_conflict_blocked(self) -> None:
        book_appointment(
            patient=self.patient_a, doctor=self.doctor, start=slot(self.day, 10)
        )
        with self.assertRaises(SlotUnavailableError):
            book_appointment(
                patient=self.patient_b, doctor=self.doctor, start=slot(self.day, 10)
            )

    def test_patient_double_booking_blocked_across_doctors(self) -> None:
        book_appointment(
            patient=self.patient_a, doctor=self.doctor, start=slot(self.day, 10, 30)
        )
        with self.assertRaises(AppointmentError):
            book_appointment(
                patient=self.patient_a,
                doctor=self.other_doctor,
                start=slot(self.day, 10, 30),
            )

    def test_leave_and_booked_slots_hidden_from_available(self) -> None:
        book_appointment(
            patient=self.patient_a, doctor=self.doctor, start=slot(self.day, 9)
        )
        DoctorLeave.objects.create(
            doctor=self.other_doctor,
            start_date=self.day,
            end_date=self.day,
            reason="conference",
        )
        doctor_slots = get_available_slots(self.doctor, self.day)
        offered_starts = [entry.start for entry in doctor_slots]
        self.assertNotIn(slot(self.day, 9), offered_starts)
        self.assertFalse(get_available_slots(self.other_doctor, self.day))


class StateMachineTests(TestCase):
    """Transitions, window rule, queue numbers, reschedule linkage."""

    def setUp(self) -> None:
        self.doctor = make_user(
            "state.doctor@example.test",
            role=make_role_with("State Doctor (t)", [perms.APPOINTMENT_VIEW_OWN]),
        )
        self.patient = make_patient("State")
        self.day = make_future_day()
        _ensure_schedule(self.doctor, self.day)
        self.tomorrow = self.day + datetime.timedelta(days=1)
        _ensure_schedule(self.doctor, self.tomorrow)
        self.appt = book_appointment(
            patient=self.patient, doctor=self.doctor, start=slot(self.day, 9)
        )

    def test_queue_number_increments_per_doctor_day(self) -> None:
        checked = check_in(appointment=self.appt, actor=None)
        self.assertEqual(checked.queue_number, 1)
        second = book_appointment(
            patient=make_patient("Second"),
            doctor=self.doctor,
            start=slot(self.day, 9, 30),
        )
        second_checked = check_in(appointment=second, actor=None)
        self.assertEqual(second_checked.queue_number, 2)

    def test_full_flow_to_completed_is_terminal(self) -> None:
        checked = check_in(appointment=self.appt, actor=None)
        start_visit(appointment=checked, actor=None)
        checked.refresh_from_db()
        self.assertEqual(checked.status, AppointmentStatus.IN_PROGRESS)
        complete_visit(appointment=checked, actor=None)
        checked.refresh_from_db()
        self.assertEqual(checked.status, AppointmentStatus.COMPLETED)
        with self.assertRaises(AppointmentError):
            cancel_appointment(appointment=checked, actor=None, reason="late cancel")

    def test_cancel_window_blocks_close_to_start(self) -> None:
        near_start = self.appt.scheduled_start = timezone.now() + timezone.timedelta(
            minutes=30
        )
        Appointment.all_objects.filter(pk=self.appt.pk).update(
            scheduled_start=near_start
        )
        self.appt.refresh_from_db()
        with self.assertRaises(AppointmentError):
            cancel_appointment(appointment=self.appt, actor=None, reason="too close")

    def test_no_show_terminal_for_missing_patient(self) -> None:
        mark_no_show(appointment=self.appt, actor=None)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, AppointmentStatus.NO_SHOW)

    def test_reschedule_keeps_history_link(self) -> None:
        new_start = slot(self.tomorrow, 9, 30)
        reschedule_appointment(
            appointment=self.appt,
            actor=None,
            new_doctor=self.doctor,
            new_start=new_start,
            reason="schedule clash",
        )
        old = Appointment.all_objects.get(pk=self.appt.pk)
        new = Appointment.objects.get(status=AppointmentStatus.SCHEDULED)
        self.assertEqual(old.status, AppointmentStatus.CANCELLED)
        self.assertTrue(old.cancellation_reason.startswith("Rescheduled"))
        self.assertEqual(new.rescheduled_from_id, old.pk)
        self.assertEqual(new.scheduled_start, new_start)


class ScreenshotPermissionTests(TestCase):
    """Backend permission enforcement for appointment screens."""

    def setUp(self) -> None:
        self.client = Client()
        self.receptionist = make_user(
            "screen.recep@example.test",
            role=make_role_with(
                "Screen Receptionist (t)",
                [
                    perms.APPOINTMENT_VIEW,
                    perms.APPOINTMENT_CHECKIN,
                    perms.SCHEDULE_VIEW,
                ],
            ),
        )
        self.doctor = make_user(
            "screen.doctor@example.test",
            role=make_role_with("Screen Doctor (t)", [perms.APPOINTMENT_VIEW_OWN]),
        )

    def test_doctor_queue_allowed_own_backend(self) -> None:
        self.client.force_login(self.doctor)
        response = self.client.get("/appointments/")
        self.assertEqual(response.status_code, 200)

    def test_book_denied_without_create(self) -> None:
        self.client.force_login(self.doctor)
        response = self.client.get(reverse("appointment_book"))
        self.assertEqual(response.status_code, 403)

    def test_schedule_manage_denied_for_view_only(self) -> None:
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse("schedule_add"))
        self.assertEqual(response.status_code, 403)
