"""Django admin for accounts models."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserAdminChangeForm, UserAdminCreationForm
from .models import Department, Permission, Role, RolePermission, StaffProfile, User


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description")


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "dashboard_template", "permission_count")
    search_fields = ("name", "description")
    inlines = [RolePermissionInline]

    @admin.display(description="permissions")
    def permission_count(self, role: Role) -> int:
        return role.permissions.count()


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_visible")
    search_fields = ("name",)

    @admin.display(boolean=True, description="visible")
    def is_visible(self, department: Department) -> bool:
        return not department.is_deleted


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "phone", "license_no")
    search_fields = ("user__email", "user__full_name", "license_no")
    list_select_related = ("user", "department")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin wired to the custom User model's email login."""

    add_form = UserAdminCreationForm
    form = UserAdminChangeForm
    model = User
    fieldsets = (
        (None, {"fields": ("email", "full_name", "password")}),
        ("Membership", {"fields": ("role", "is_staff", "is_superuser", "is_active")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )
    list_display = ("email", "full_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "full_name")
    ordering = ("email",)
    list_select_related = ("role",)
    readonly_fields = ("last_login", "date_joined")
    filter_horizontal = ("groups", "user_permissions")
