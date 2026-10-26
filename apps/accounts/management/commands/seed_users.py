"""seed_users: create one fake staff user per role.

Safety rules:
- refuses to run unless settings.DEBUG is True;
- passwords come only from SEED_DEFAULT_PASSWORD (env), never from code;
- idempotent: run twice => same users, no duplicates.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Department, Role, StaffProfile, User
from apps.accounts.seed_data import DEPARTMENTS, USERS


class Command(BaseCommand):
    help = "Seed demo users and departments from seed_data.py"

    @transaction.atomic
    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        if not settings.DEBUG:
            raise CommandError(
                "seed_users only runs when DEBUG=True (demo data protection)."
            )
        password = getattr(settings, "SEED_DEFAULT_PASSWORD", "")
        if not password:
            raise CommandError(
                "SEED_DEFAULT_PASSWORD is not set; add it to .env (see .env.example)."
            )
        if len(password) < 10:
            raise CommandError("SEED_DEFAULT_PASSWORD must be at least 10 characters.")

        for spec in DEPARTMENTS:
            Department.all_objects.get_or_create(name=spec["name"], defaults=spec)

        created_users = 0
        for spec in USERS:
            role = Role.objects.filter(name=spec["role"]).first()
            if role is None:
                raise CommandError(
                    f"Role '{spec['role']}' is missing — run `manage.py seed_roles` first."
                )
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "full_name": spec["full_name"],
                    "role": role,
                    "is_superuser": spec["is_superuser"],
                    "is_staff": spec["is_staff"],
                },
            )
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])
            if created or not user.check_password(password):
                user.set_password(password)
                user.save(update_fields=["password"])
            department = Department.objects.filter(name=spec["department"]).first()
            profile, _ = StaffProfile.all_objects.get_or_create(user=user)
            profile.department = department
            profile.license_no = spec["license_no"]
            profile.save()
            created_users += int(created)
        self.stdout.write(f"Users: {User.objects.count()} total, {created_users} new")
        self.stdout.write(self.style.SUCCESS("seed_users finished"))
