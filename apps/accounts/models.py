"""Custom User model with email login, plus RBAC models."""
from typing import Any

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class UserManager(BaseUserManager):
    """Manager for the email-based custom user."""

    use_in_migrations = True

    @staticmethod
    def _normalize(email: str) -> str:
        return email.casefold().strip()

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self._normalize(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self.create_user(email, password, **extra)


class Permission(models.Model):
    """A named capability granted to roles (e.g. "user.view")."""

    code = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class Role(models.Model):
    """A set of permissions plus a data-driven dashboard template."""

    name = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True)
    dashboard_template = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=(
            "Template path for this role's dashboard. Empty value falls back "
            "to the generic dashboard."
        ),
    )
    permissions = models.ManyToManyField(Permission, through="RolePermission", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RolePermission(models.Model):
    """Join table role <-> permission."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="permission_roles"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("role", "permission"), name="unique_role_permission")
        ]

    def __str__(self) -> str:
        return f"{self.role.name}: {self.permission.code}"


class Department(BaseModel):
    """A hospital department."""

    name = models.CharField(max_length=128, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(AbstractBaseUser, PermissionsMixin):
    """Email-login user with a role and optional staff profile."""

    email = models.EmailField("email address", unique=True, db_index=True)
    full_name = models.CharField(max_length=255)
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.PROTECT, related_name="users"
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = ["full_name"]

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.casefold().strip()
        super().save(*args, **kwargs)


class StaffProfile(BaseModel):
    """Extra HR info for a user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staffprofile")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="staff"
    )
    phone = models.CharField(max_length=32, blank=True)
    license_no = models.CharField(
        max_length=64, blank=True, validators=[MinLengthValidator(4)], help_text="If licensed role."
    )

    def __str__(self) -> str:
        return f"Profile: {self.user.email}"
