"""Module registry: the single data definition of the app's navigation.

The sidebar and dashboard action cards are generated from these entries,
filtered by permission. Later phases add modules by appending entries here —
no existing template or view code changes.

Entry fields:
  key        stable identifier (used in tests)
  label      display text
  icon       id of an SVG sprite symbol (see templates/components/icons.html)
  url_name   Django URL name to reverse; None => never linked directly
  permission required permission code; None => any authenticated user
  in_nav     show in the sidebar when permitted
  in_dashboard show as an action card when permitted
  active     False => "Coming soon" placeholder (never in the sidebar)
"""
from django.urls import reverse

from core.permissions import (
    AUDIT_VIEW,
    DEPARTMENT_VIEW,
    ROLE_VIEW,
    STAFF_VIEW,
    STYLEGUIDE_VIEW,
    USER_VIEW,
)

DASHBOARD = {
    "key": "dashboard",
    "label": "Dashboard",
    "icon": "dashboard",
    "url_name": "dashboard",
    "permission": None,
    "in_nav": True,
    "in_dashboard": False,
    "active": True,
}

MODULES: list[dict] = [
    {
        "key": "users",
        "label": "Users",
        "icon": "people",
        "url_name": "user_list",
        "permission": USER_VIEW,
        "in_nav": True,
        "in_dashboard": True,
        "active": True,
    },
    {
        "key": "roles",
        "label": "Roles & permissions",
        "icon": "badge",
        "url_name": "role_list",
        "permission": ROLE_VIEW,
        "in_nav": True,
        "in_dashboard": True,
        "active": True,
    },
    {
        "key": "departments",
        "label": "Departments",
        "icon": "department",
        "url_name": "department_list",
        "permission": DEPARTMENT_VIEW,
        "in_nav": True,
        "in_dashboard": True,
        "active": True,
    },
    {
        "key": "staff",
        "label": "Staff directory",
        "icon": "id_card",
        "url_name": "staff_list",
        "permission": STAFF_VIEW,
        "in_nav": True,
        "in_dashboard": True,
        "active": True,
    },
    {
        "key": "audit",
        "label": "Audit log",
        "icon": "history",
        "url_name": "audit_list",
        "permission": AUDIT_VIEW,
        "in_nav": True,
        "in_dashboard": True,
        "active": True,
    },
    {
        "key": "styleguide",
        "label": "Styleguide",
        "icon": "palette",
        "url_name": "styleguide",
        "permission": STYLEGUIDE_VIEW,
        "in_nav": True,
        "in_dashboard": False,
        "active": True,
    },
    # -------------------------------------------------- later-phase modules
    {
        "key": "patients",
        "label": "Patients",
        "icon": "person",
        "url_name": None,
        "permission": None,
        "in_nav": False,
        "in_dashboard": True,
        "active": False,
    },
    {
        "key": "appointments",
        "label": "Appointments",
        "icon": "calendar",
        "url_name": None,
        "permission": None,
        "in_nav": False,
        "in_dashboard": True,
        "active": False,
    },
    {
        "key": "admissions",
        "label": "Admissions",
        "icon": "bed",
        "url_name": None,
        "permission": None,
        "in_nav": False,
        "in_dashboard": True,
        "active": False,
    },
    {
        "key": "pharmacy_module",
        "label": "Pharmacy",
        "icon": "pill",
        "url_name": None,
        "permission": None,
        "in_nav": False,
        "in_dashboard": True,
        "active": False,
    },
    {
        "key": "billing",
        "label": "Billing",
        "icon": "receipt",
        "url_name": None,
        "permission": None,
        "in_nav": False,
        "in_dashboard": True,
        "active": False,
    },
]


def permitted_modules(user, request=None) -> list[dict]:
    """Return registry entries visible to ``user``, with resolved URLs.

    Cached on the request so the sidebar and dashboard resolve once. The
    Dashboard pseudo-entry is listed only for authenticated users.
    """
    if request is not None and hasattr(request, "_nav_cache"):
        return request._nav_cache
    from core.permissions import user_has_permission  # local import: no cycle

    visible: list[dict] = [dict(DASHBOARD)]
    entries: list[dict] = []
    for entry in MODULES:
        if entry["permission"] is not None and not user_has_permission(
            user, entry["permission"], request=request
        ):
            continue
        item = dict(entry)
        item["url"] = reverse(item["url_name"]) if item["url_name"] else None
        entries.append(item)
    result = visible + entries
    if request is not None:
        request._nav_cache = result
    return result
