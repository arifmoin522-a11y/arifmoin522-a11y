"""Single source of truth for permission codes and the runtime check.

Every permission code is defined ONCE here. Views import the constants,
and the seed command reads ``PERMISSION_DESCRIPTIONS`` to create
``accounts.Permission`` rows. No code may use raw permission strings.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from apps.accounts.models import User


# ---------------------------------------------------------------- constants
USER_VIEW = "user.view"
USER_CREATE = "user.create"
USER_EDIT = "user.edit"
USER_DELETE = "user.delete"
ROLE_VIEW = "role.view"
ROLE_CREATE = "role.create"
ROLE_EDIT = "role.edit"
ROLE_DELETE = "role.delete"
DEPARTMENT_VIEW = "department.view"
DEPARTMENT_EDIT = "department.edit"
STAFF_VIEW = "staff.view"
STAFF_EDIT = "staff.edit"
AUDIT_VIEW = "audit.view"
STYLEGUIDE_VIEW = "styleguide.view"  # superuser convenience; never granted to roles

#: code -> human description, consumed by the seed_roles management command
PERMISSION_DESCRIPTIONS: dict[str, str] = {
    USER_VIEW: "View user accounts",
    USER_CREATE: "Create user accounts",
    USER_EDIT: "Edit user accounts",
    USER_DELETE: "Deactivate user accounts",
    ROLE_VIEW: "View roles",
    ROLE_CREATE: "Create roles",
    ROLE_EDIT: "Edit roles",
    ROLE_DELETE: "Remove roles",
    DEPARTMENT_VIEW: "View departments",
    DEPARTMENT_EDIT: "Create and edit departments",
    STAFF_VIEW: "View staff profiles",
    STAFF_EDIT: "Edit staff profiles",
    AUDIT_VIEW: "View the audit log",
    STYLEGUIDE_VIEW: "Open the UI styleguide (superusers only)",
}


# ------------------------------------------------------------- runtime check
def get_permission_codes(
    user: "User",
    request: "HttpRequest | None" = None,
) -> "set[str] | None":
    """Return the user's permission codes, or ``None`` for a superuser.

    ``None`` is the superuser-bypass sentinel. When a request is given the
    result is cached on the request object (per request, never globally).
    """
    if request is not None and getattr(request, "_perm_cache", None) is not None:
        return request._perm_cache
    if not user.is_authenticated:
        codes: set[str] | None = set()
    elif user.is_superuser:
        codes = None
    else:
        role = getattr(user, "role", None)
        codes = (
            set(role.permissions.values_list("code", flat=True))
            if role is not None
            else set()
        )
    if request is not None and codes is not None:
        request._perm_cache = codes
    return codes


def user_has_permission(user, code: str, request=None) -> bool:
    """Return True when the user holds ``code``. Superusers always pass."""
    if not getattr(user, "is_authenticated", False):
        return False
    codes = get_permission_codes(user, request=request)
    return True if codes is None else code in codes
