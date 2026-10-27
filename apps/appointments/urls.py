"""Appointment, schedule and leave URL routes (registry names bound here)."""
from django.urls import path

from . import views

urlpatterns = [
    path("appointments/", views.appointment_list, name="appointment_list"),
    path("appointments/book/", views.appointment_book, name="appointment_book"),
    path("appointments/<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("appointments/<int:pk>/check-in/", views.appointment_checkin, name="appointment_checkin"),
    path("appointments/<int:pk>/start/", views.appointment_start, name="appointment_start"),
    path("appointments/<int:pk>/complete/", views.appointment_complete, name="appointment_complete"),
    path("appointments/<int:pk>/cancel/", views.appointment_cancel, name="appointment_cancel"),
    path("appointments/<int:pk>/reschedule/", views.appointment_reschedule, name="appointment_reschedule"),
    path("appointments/<int:pk>/no-show/", views.appointment_no_show, name="appointment_no_show"),
    path("appointments/week/", views.week_calendar, name="week_calendar"),
    path("schedules/", views.schedule_list, name="schedule_list"),
    path("schedules/add/", views.schedule_add, name="schedule_add"),
    path("schedules/<int:pk>/edit/", views.schedule_edit, name="schedule_edit"),
    path("schedules/<int:pk>/remove/", views.schedule_remove, name="schedule_remove"),
    path("schedules/leave/add/", views.leave_add, name="leave_add"),
    path("schedules/leave/<int:pk>/remove/", views.leave_remove, name="leave_remove"),
]
