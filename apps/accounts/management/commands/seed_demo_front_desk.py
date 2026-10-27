"""seed_demo_front_desk: demo patients, schedules, leave and appointments.

Safety rules:
- refuses to run unless settings.DEBUG is True;
- idempotent: everything is get_or_create'd from fixed names/seed data;
- the random layout uses a fixed seed so reruns are stable;
- no phone numbers or names outside the clearly-fake .test set.
"""
import datetime
import random
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.appointments.constants import AppointmentStatus
from apps.appointments.models import Appointment, DoctorLeave, DoctorSchedule
from apps.patients.constants import BloodGroup, Gender
from apps.patients.models import Patient

FIRST_NAMES = [
    "Ayesha", "Rohan", "Mehdi", "Sara", "Dinesh", "Leila", "Omar", "Priya", "Tanya",
    "Yusuf", "Nadia", "Faruk", "Heena", "Imran", "Jamal", "Kiran", "Lubna", "Maya",
    "Nikhil", "Rashid", "Seema", "Tariq", "Uzma", "Victor", "Warda", "Xavier",
]
LAST_NAMES = [
    "Ahmed", "Begum", "Chowdhury", "Das", "Farooq", "Gill", "Hossain", "Iqbal",
    "Jahan", "Karim", "Lodhi", "Mirza", "Nawaz", "Owais", "Patel", "Qureshi",
]
DOCTOR_EMAILS = [
    "doctor@example.test",
    "doctor.emergency@example.test",
    "doctor.pediatrics@example.test",
    "doctor.radiology@example.test",
]
SCHEDULE_HOURS = {
    "doctor@example.test": (9, 13),
    "doctor.emergency@example.test": (9, 11),
    "doctor.pediatrics@example.test": (10, 13),
    "doctor.radiology@example.test": (11, 13),
}
PAST_STATUSES = (
    AppointmentStatus.COMPLETED,
    AppointmentStatus.COMPLETED,
    AppointmentStatus.NO_SHOW,
    AppointmentStatus.CANCELLED,
)


def _demo_status(index: int, day: datetime.date, today: datetime.date) -> str:
    """Deterministic mixed statuses for demo variety."""
    if day < today:
        return PAST_STATUSES[index % len(PAST_STATUSES)]
    if day == today and index % 3 == 0:
        return AppointmentStatus.CHECKED_IN
    return AppointmentStatus.SCHEDULED


class Command(BaseCommand):
    help = "Seed demo patients, schedules, leave and appointments (DEBUG only)"

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:  # type: ignore[no-untyped-def]
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo_front_desk only runs when DEBUG=True (demo data protection)."
            )

        rng = random.Random(20261)
        created_patients = 0
        for index in range(1, 31):
            number = 20 + index
            patient, created = Patient.all_objects.get_or_create(
                patient_code=_make_code(settings.PATIENT_CODE_PREFIX, number),
                defaults={
                    "first_name": rng.choice(FIRST_NAMES),
                    "last_name": rng.choice(LAST_NAMES),
                    "date_of_birth": datetime.date(1955, 1, 1)
                    + datetime.timedelta(days=rng.randint(0, 35_000)),
                    "gender": rng.choice(Gender.values),
                    "blood_group": rng.choice(BloodGroup.values),
                    "phone": f"+8801{''.join(rng.choices('3457', k=2))}02160{number:04d}",
                },
            )
            created_patients += int(created)
        self.stdout.write(f"Patients: {created_patients} new")

        doctors: list[User] = []
        for email in DOCTOR_EMAILS:
            user = User.objects.filter(email=email).first()
            if user is None:
                raise CommandError(
                    f"{email} not found — run `manage.py seed_users` and `seed_roles` first."
                )
            doctors.append(user)

        created_schedules = 0
        for doctor in doctors:
            start_hour, end_hour = SCHEDULE_HOURS[str(doctor.email)]
            for weekday in range(5):
                _, created = DoctorSchedule.objects.get_or_create(
                    doctor=doctor,
                    weekday=weekday,
                    start_time=datetime.time(start_hour, 0),
                    defaults={
                        "end_time": datetime.time(end_hour, 0),
                        "slot_minutes": settings.APPOINTMENT_SLOT_MINUTES,
                    },
                )
                created_schedules += int(created)
        self.stdout.write(f"Schedules: {created_schedules} new")

        leave_doctor = doctors[-1]
        today = timezone.localdate()
        DoctorLeave.objects.get_or_create(
            doctor=leave_doctor,
            start_date=today,
            defaults={
                "end_date": today + datetime.timedelta(days=30),
                "reason": "Phase 2 demo leave window (30 days).",
            },
        )
        self.stdout.write(
            f"Leave for {leave_doctor.email}: {today:%Y-%m-%d} to +30 days"
        )

        patients = list(
            Patient.all_objects.filter(patient_code__startswith="PAT-").order_by("pk")
        )
        created_appointments = 0
        for index in range(30):
            doctor = doctors[index % len(doctors)]
            patient = patients[index % len(patients)]
            day = today + datetime.timedelta(days=(index % 7) - 2)
            slot_hour = 9 + (index % 4)
            slot_minute = 30 if index % 2 else 0
            start = timezone.make_aware(
                datetime.datetime.combine(day, datetime.time(slot_hour, slot_minute)),
                timezone.get_current_timezone(),
            )
            appointment, created = Appointment.all_objects.get_or_create(
                patient=patient,
                doctor=doctor,
                scheduled_start=start,
                defaults={
                    "scheduled_end": start + datetime.timedelta(
                        minutes=settings.APPOINTMENT_SLOT_MINUTES
                    ),
                    "status": _demo_status(index, day, today),
                    "reason": f"Demo appointment #{index + 1}",
                },
            )
            if created and appointment.status in (
                AppointmentStatus.CHECKED_IN.value,
                AppointmentStatus.COMPLETED.value,
            ):
                # queue numbers only make sense for checked-in rows
                if appointment.status == AppointmentStatus.CHECKED_IN.value:
                    appointment.queue_number = (index % 4) + 1
                    appointment.save(update_fields=["queue_number"])
            created_appointments += int(created)
        count = Appointment.all_objects.count()
        self.stdout.write(f"Appointments: {created_appointments} new, {count} total")
        self.stdout.write(self.style.SUCCESS("seed_demo_front_desk finished"))


def _make_code(prefix: str, number: int) -> str:
    """Stable demo patient code (independent of the live sequence)."""
    return f"{prefix}-{number:0{settings.CODE_SEQUENCE_DIGITS}d}"
