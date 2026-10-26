"""seed_roles: create permissions, roles and role->permission links.

Idempotent: uses get_or_create / update_or_create, safe to run repeatedly.
Data lives exclusively in apps/accounts/seed_data.py.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission, Role, RolePermission
from apps.accounts.seed_data import PERMISSIONS, ROLES


class Command(BaseCommand):
    help = "Seed permissions, roles and role permissions from seed_data.py"

    @transaction.atomic
    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        created_permissions = 0
        for code, description in PERMISSIONS.items():
            _, created = Permission.objects.get_or_create(
                code=code, defaults={"description": description}
            )
            created_permissions += int(created)
        self.stdout.write(f"Permissions: {Permission.objects.count()} total, {created_permissions} new")

        created_roles = 0
        for spec in ROLES:
            role, created = Role.objects.get_or_create(name=spec["name"])
            role.description = spec["description"]
            role.dashboard_template = spec["dashboard_template"]
            role.save()
            for code in spec["permissions"]:
                permission = Permission.objects.get(code=code)
                RolePermission.objects.get_or_create(
                    role=role, permission=permission
                )
            created_roles += int(created)
        self.stdout.write(f"Roles: {Role.objects.count()} total, {created_roles} new")

        self.stdout.write(self.style.SUCCESS("seed_roles finished"))
