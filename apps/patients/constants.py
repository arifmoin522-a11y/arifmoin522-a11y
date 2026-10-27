"""Patients phase constants: the only place gender/blood-group values exist.

Templates receive display metadata through model helper properties, so no
template or view ever spells out a status value.
"""
from django.db import models


class Gender(models.TextChoices):
    """Patient gender; "Other" and "Prefer not to say" kept explicit."""

    FEMALE = "F", "Female"
    MALE = "M", "Male"
    OTHER = "OTH", "Other"
    NOT_STATED = "NS", "Prefer not to say"


class BloodGroup(models.TextChoices):
    """Optional clinical blood group."""

    A_POS = "A+", "A+"
    A_NEG = "A-", "A-"
    B_POS = "B+", "B+"
    B_NEG = "B-", "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS = "O+", "O+"
    O_NEG = "O-", "O-"


#: name used as the CodeSequence key for patient codes (never changed)
SEQUENCE_PATIENT = "patient_code"
