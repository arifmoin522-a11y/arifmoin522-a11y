"""Forms for booking, schedule and leave management (all validated server-side)."""
import datetime

from django import forms
from django.utils import timezone

from apps.accounts.models import Department

from .models import (
    Appointment,
    DoctorLeave,
    DoctorSchedule,
    doctor_capable_check,
    doctor_capable_users,
)


class BookConfirmForm(forms.Form):
    """Final confirmation step of the booking flow."""

    reason = forms.CharField(
        label="Reason for visit",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    department = forms.ModelChoiceField(
        label="Department",
        queryset=Department.objects.all(),
        required=False,
        empty_label="— not set —",
    )

    def clean_reason(self) -> str:
        return (self.cleaned_data.get("reason") or "").strip()


class CancelForm(forms.Form):
    """Cancel / reschedule reason; POST-only endpoints require it."""

    reason = forms.CharField(
        label="Reason",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_reason(self) -> str:
        return (self.cleaned_data.get("reason") or "").strip()


class RescheduleForm(CancelForm):
    """Reason plus the doctor / date picked through the slot flow."""

    doctor = forms.ModelChoiceField(
        label="Doctor",
        queryset=doctor_capable_users().order_by("full_name"),
    )
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean_date(self) -> datetime.date:
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("Rescheduling into the past is not allowed.")
        return date


class DoctorScheduleForm(forms.ModelForm):
    """Weekly availability; doctor list comes from the permission, not roles."""

    class Meta:
        model = DoctorSchedule
        fields = ("doctor", "weekday", "start_time", "end_time", "slot_minutes", "is_active")
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = doctor_capable_users().order_by("full_name")

    def clean(self) -> dict:
        cleaned = super().clean()
        doctor = cleaned.get("doctor")
        weekday = cleaned.get("weekday")
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")
        if not (doctor and weekday is not None and start and end):
            return cleaned
        if not doctor_capable_check(doctor):
            self.add_error("doctor", "Selected user's role cannot consult appointments.")
        if end <= start:
            self.add_error("end_time", "End time must be after start time.")
        overlapping = DoctorSchedule.objects.filter(
            doctor=doctor, weekday=weekday, is_active=True
        ).exclude(pk=self.instance.pk)
        if overlapping.filter(start_time__lt=end, end_time__gt=start).exists():
            self.add_error(
                None, "This doctor already has an overlapping schedule that day."
            )
        return cleaned


class DoctorLeaveForm(forms.ModelForm):
    """Leave windows; validated the same way as schedules."""

    class Meta:
        model = DoctorLeave
        fields = ("doctor", "start_date", "end_date", "reason")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = doctor_capable_users().order_by("full_name")

    def clean(self) -> dict:
        cleaned = super().clean()
        doctor = cleaned.get("doctor")
        if doctor is not None and not doctor_capable_check(doctor):
            self.add_error("doctor", "Selected user's role cannot consult appointments.")
        if cleaned.get("start_date") and cleaned.get("end_date"):
            if cleaned["end_date"] < cleaned["start_date"]:
                self.add_error("end_date", "End date cannot be before start date.")
        return cleaned
