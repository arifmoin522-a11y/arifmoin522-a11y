"""Abstract base model with audit fields and soft-delete support."""
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from apps.accounts.models import User


class ActiveManager(models.Manager):
    """Default manager that hides soft-deleted records."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    """Abstract base: timestamps, creator and soft-delete support.

    ``objects`` excludes deleted rows; ``all_objects`` includes them.
    Records are never hard-deleted — call ``soft_delete()``.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user: "User | None" = None) -> None:
        """Flag this record as deleted instead of removing it from the DB."""
        self.is_deleted = True
        update_fields: list[str] = ["is_deleted", "updated_at"]
        if user is not None and "created_by" in {f.name for f in self._meta.fields}:
            self.created_by = user
            update_fields.append("created_by")
        self.save(update_fields=update_fields)

    def delete(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError(
            "Hard delete is disabled — use soft_delete() instead."
        )
