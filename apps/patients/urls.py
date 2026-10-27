"""Patient URLs (projectId-agnostic name list without a namespace)."""
from django.urls import path

from . import views

urlpatterns = [
    path("patients/", views.patient_list, name="patient_list"),
    path("patients/search/clear/", views.patient_search_clear, name="patient_search_clear"),
    path("patients/add/", views.patient_add, name="patient_add"),
    path("patients/<int:pk>/", views.patient_detail, name="patient_detail"),
    path("patients/<int:pk>/edit/", views.patient_edit, name="patient_edit"),
    path("patients/<int:pk>/remove/", views.patient_remove, name="patient_remove"),
    path("patients/<int:pk>/contacts/add/", views.contact_add, name="contact_add"),
    path("contacts/<int:contact_pk>/primary/", views.contact_primary, name="contact_primary"),
]
