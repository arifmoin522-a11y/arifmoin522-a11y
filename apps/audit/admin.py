"""Append-only audit model administration helpers."""
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only admin: audit entries can neither be edited nor deleted."""

    list_display = ("timestamp", "user", "action", "object_type", "object_id", "ip_address")
    list_filter = ("action",)
    search_fields = ("details", "user__email", "object_type", "object_id")
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def get_actions(self, request):  # type: ignore[no-untyped-def]
        return []
