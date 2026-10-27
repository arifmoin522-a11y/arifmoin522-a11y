"""Append-only audit trail. Records are never updated or deleted."""
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from apps.accounts.models import User


class AuditLog(models.Model):
    """Immutable record of security-relevant actions."""

    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        LOGIN_FAILED = "LOGIN_FAILED", "Failed login"
        LOGIN_LOCKED = "LOGIN_LOCKED", "Login locked out"
        VIEW = "VIEW", "Viewed"
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        PERMISSION_DENIED = "PERMISSION_DENIED", "Permission denied"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    object_type = models.CharField(max_length=255, blank=True)
    object_id = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["user"]),
            models.Index(fields=["action"]),
        ]
        verbose_name = "audit log entry"
        verbose_name_plural = "audit log entries"

    def __str__(self) -> str:
        actor = self.user.email if self.user_id else "anonymous"
        return f"{self.timestamp:%Y-%m-%d %H:%M} {actor} {self.action}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        if not self._state.adding:
            raise NotImplementedError("AuditLog entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError("AuditLog entries can never be deleted.")
