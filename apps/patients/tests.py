"""Patient front-desk tests: permissions, masking, contacts, duplicates.

Run with: python manage.py test apps.patients
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Permission, Role
from apps.patients.constants import Gender
from apps.patients.models import EmergencyContact, Patient
from apps.patients.selectors import display_phone
from apps.patients.services import (
    add_contact,
    find_duplicate_patients,
    make_contact_primary,
)
from core import permissions as perms

from apps.accounts.tests import make_user


def make_role_with(name: str, codes: list[str]) -> Role:
    """Role with the given permission codes (or only name when empty)."""
    role = Role.objects.create(name=name)
    for code in codes:
        permission, _ = Permission.objects.get_or_create(
            code=code, defaults={"description": code}
        )
        role.permissions.add(permission)
    return role


def make_patient(**overrides) -> Patient:
    payload = dict(
        first_name="Test",
        last_name="Case",
        date_of_birth=datetime.date(1990, 2, 2),
        gender=Gender.FEMALE,
        phone="01711-223344",
    )
    payload.update(overrides)
    return Patient.objects.create(**payload)


class PatientCodeTests(TestCase):
    def test_create_assigns_patient_code(self) -> None:
        patient = make_patient()
        self.assertTrue(patient.patient_code.startswith("PAT-"))

    def test_unique_patient_code(self) -> None:
        first = make_patient()
        second = make_patient(last_name="Other")
        self.assertNotEqual(first.patient_code, second.patient_code)

    def test_dob_future_rejected(self) -> None:
        with self.assertRaises(Exception):
            make_patient(date_of_birth=datetime.date.today() + datetime.timedelta(days=1))


class ContactTests(TestCase):
    def setUp(self) -> None:
        self.patient = make_patient()
        self.nurse = make_user("nurse.contact@example.test")
        EmergencyContactForm = None  # forms exercised through services only

    def _contact_form(self, **kw):
        from apps.patients.forms import EmergencyContactForm

        base = {"name": "Mom", "phone": "555-111000", "relationship": "Mother"}
        base.update(kw)
        return EmergencyContactForm(base)

    def test_add_contact_and_primary_cascade(self) -> None:
        form = self._contact_form()
        self.assertTrue(form.is_valid(), form.errors)
        first = add_contact(patient=self.patient, form=form, user=self.nurse)
        self.assertFalse(first.is_primary)
        form2 = self._contact_form(name="Dad", phone="555-222000")
        self.assertTrue(form2.is_valid(), form2.errors)
        second = add_contact(patient=self.patient, form=form2, user=self.nurse)
        make_contact_primary(contact=second, user=self.nurse)
        second.refresh_from_db()
        self.assertTrue(second.is_primary)
        for contact in self.patient.contacts.exclude(pk=second.pk).all():
            contact.refresh_from_db()
            self.assertFalse(contact.is_primary)

    def test_duplicate_finder_name_dob_phone(self) -> None:
        found = find_duplicate_patients(
            self.patient.first_name,
            self.patient.last_name,
            self.patient.date_of_birth,
            self.patient.phone,
        )
        self.assertTrue(found.filter(pk=self.patient.pk).exists())
        miss = find_duplicate_patients(
            self.patient.first_name,
            "Nobody",
            self.patient.date_of_birth,
            self.patient.phone,
        )
        self.assertFalse(miss.exists())


class PrivacyTests(TestCase):
    def setUp(self) -> None:
        self.patient = make_patient()
        self.reception_role = make_role_with(
            "FD Receptionist (t)", [perms.PATIENT_VIEW_CONTACT]
        )
        self.plain_role = make_role_with("FD Viewer (t)", [perms.PATIENT_VIEW])
        self.receptionist = make_user("fd.recep@example.test", role=self.reception_role)
        self.viewer = make_user("fd.viewer@example.test", role=self.plain_role)

    def test_mask_keeps_last_three_digits_only(self) -> None:
        masked = display_phone(self.patient, self.viewer)
        self.assertNotEqual(masked, "01711-223344")
        self.assertTrue(masked.endswith("344"))

    def test_view_contact_permission_sees_full_phone(self) -> None:
        self.assertEqual(display_phone(self.patient, self.receptionist), "01711-223344")


class PatientScreenPermissionTests(TestCase):
    """Sidebar-independent backend enforcement (403 templates, audit)."""

    def setUp(self) -> None:
        self.client = Client()
        self.patient = make_patient()
        self.viewer_role = make_role_with("Viewer Only (t)", [perms.PATIENT_VIEW])
        self.creator_role = make_role_with(
            "Creater (t)",
            [perms.PATIENT_VIEW, perms.PATIENT_CREATE, perms.PATIENT_UPDATE],
        )
        self.viewer = make_user("screen.viewer@example.test", role=self.viewer_role)
        self.creator = make_user("screen.creator@example.test", role=self.creator_role)

    def test_detail_allowed_for_viewer(self) -> None:
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("patient_detail", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)

    def test_register_denied_without_patient_create(self) -> None:
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("patient_add"))
        self.assertEqual(response.status_code, 403)

    def test_register_allowed_for_creator(self) -> None:
        self.client.force_login(self.creator)
        response = self.client.get(reverse("patient_add"))
        self.assertEqual(response.status_code, 200)
        DemoUser = get_user_model()
        self.assertTrue(DemoUser.objects.filter(email="screen.creator@example.test").exists())
