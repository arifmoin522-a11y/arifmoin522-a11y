"""Django admin for patient models."""
from django.contrib import admin
from django.utils.html import format_html

from .models import EmergencyContact, Patient


class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["fields"] = ("name", "relationship", "phone", "is_primary")
        return super().get_formset(request, obj, **kwargs)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("patient_code", "full_name_display", "date_of_birth", "phone", "is_visible")
    search_fields = (
        "patient_code",
        "first_name",
        "last_name",
        "phone",
        "email",
    )
    list_filter = ("gender", "blood_group")
    inlines = [EmergencyContactInline]

    @admin.display(description="name", ordering="last_name")
    def full_name_display(self, patient: Patient) -> str:
        return patient.full_name

    @admin.display(boolean=True, description="visible")
    def is_visible(self, patient: Patient) -> bool:
        return not patient.is_deleted

    def get_queryset(self, request):  # type: ignore[no-untyped-def]
        return Patient.all_objects.all()

    def save_model(self, request, obj, form, change):  # type: ignore[no-untyped-def]
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
