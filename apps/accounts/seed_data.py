"""Single data source for seeded permissions, roles, departments and users.

Rule 11: adding a role, permission, department or demo user is a change to
THIS FILE ONLY (plus admin seeding via the admin panel). Views, templates
and decorators never special-case roles; they check permission codes that
already exist here or in core/permissions.py.
"""
from core import permissions as p

PERMISSIONS: dict[str, str] = dict(p.PERMISSION_DESCRIPTIONS)

ROLES: list[dict] = [
    {
        "name": "Super Admin",
        "description": "Hospital system administrator; manages users, roles and audit.",
        "dashboard_template": "dashboards/admin.html",
        "permissions": list(PERMISSIONS.keys()),
    },
    {
        "name": "Doctor",
        "description": "Clinical staff; will own patients, appointments and clinical modules.",
        "dashboard_template": "dashboards/clinical.html",
        "permissions": [p.DEPARTMENT_VIEW, p.STAFF_VIEW],
    },
    {
        "name": "Nurse",
        "description": "Ward staff; will own wards and clinical records.",
        "dashboard_template": "dashboards/clinical.html",
        "permissions": [p.STAFF_VIEW],
    },
    {
        "name": "Receptionist",
        "description": "Front desk; will own registration and scheduling.",
        "dashboard_template": "dashboards/reception.html",
        "permissions": [p.DEPARTMENT_VIEW],
    },
    {
        "name": "Pharmacist",
        "description": "Pharmacy counter; will own stock and dispensing.",
        "dashboard_template": "dashboards/pharmacy.html",
        "permissions": [],
    },
    {
        "name": "Lab Technician",
        "description": "Laboratory staff; will own samples and results.",
        "dashboard_template": "dashboards/lab.html",
        "permissions": [],
    },
    {
        "name": "Accountant",
        "description": "Finance; will own billing and invoices.",
        "dashboard_template": "dashboards/finance.html",
        "permissions": [p.AUDIT_VIEW, p.DEPARTMENT_VIEW],
    },
]

DEPARTMENTS: list[dict] = [
    {"name": "Emergency", "description": "Emergency department"},
    {"name": "Internal Medicine", "description": "Adult internal medicine"},
    {"name": "Pediatrics", "description": "Children's ward"},
    {"name": "Radiology", "description": "Imaging and diagnostics"},
    {"name": "Administration", "description": "Back office, HR and finance"},
]

USERS: list[dict] = [
    {
        "email": "admin@example.test",
        "full_name": "Ada Admin",
        "role": "Super Admin",
        "is_superuser": True,
        "is_staff": True,
        "department": "Administration",
        "license_no": "",
    },
    {
        "email": "doctor@example.test",
        "full_name": "Dolores Doctor",
        "role": "Doctor",
        "is_superuser": False,
        "is_staff": False,
        "department": "Internal Medicine",
        "license_no": "DOC-0001",
    },
    {
        "email": "nurse@example.test",
        "full_name": "Nora Nurse",
        "role": "Nurse",
        "is_superuser": False,
        "is_staff": False,
        "department": "Internal Medicine",
        "license_no": "NUR-0001",
    },
    {
        "email": "reception@example.test",
        "full_name": "Rita Receptionist",
        "role": "Receptionist",
        "is_superuser": False,
        "is_staff": False,
        "department": "Administration",
        "license_no": "",
    },
    {
        "email": "pharmacist@example.test",
        "full_name": "Pablo Pharmacist",
        "role": "Pharmacist",
        "is_superuser": False,
        "is_staff": False,
        "department": "Radiology",
        "license_no": "PHA-0001",
    },
    {
        "email": "labtech@example.test",
        "full_name": "Lucy Lab",
        "role": "Lab Technician",
        "is_superuser": False,
        "is_staff": False,
        "department": "Radiology",
        "license_no": "LAB-0001",
    },
    {
        "email": "accountant@example.test",
        "full_name": "Alma Accountant",
        "role": "Accountant",
        "is_superuser": False,
        "is_staff": False,
        "department": "Administration",
        "license_no": "",
    },
]
