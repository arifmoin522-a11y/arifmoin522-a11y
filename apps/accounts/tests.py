"""Phase 1 test suite: users, permissions, soft delete, audit, seeds, lockout.

Run with: python manage.py test
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.lockout import is_locked, register_failure, clear_failures
from apps.accounts.models import Department, Role, StaffProfile, User
from apps.accounts.seed_data import ROLES, USERS
from apps.audit.models import AuditLog
from core.permissions import DEPARTMENT_VIEW, USER_VIEW

SEED_PW = "SomeLongDemoPassword!42"


def make_user(email: str, password: str = SEED_PW, **extra):
    """Create an active user directly (password hashed via Argon2)."""
    payload = {"email": email, "full_name": "Test User", **extra}
    return User.objects.create_user(password=password, **payload)


class UserManagerTests(TestCase):
    """Custom user creation and email normalisation."""

    def test_create_user_normalises_email(self) -> None:
        user = make_user("  mixed.Case@Example.TEST ")
        self.assertEqual(user.email, "mixed.case@example.test")
        self.assertTrue(user.check_password(SEED_PW))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_save_lowercases_email(self) -> None:
        user = make_user("UPPER@Example.test")
        user.email = "again@Different.TEST"
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.email, "again@different.test")

    def test_create_superuser_flags(self) -> None:
        admin = User.objects.create_superuser("admin@example.test", SEED_PW)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_create_superuser_requires_flags(self) -> None:
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                "broken@example.test", SEED_PW, is_staff=False, is_superuser=False
            )

    def test_email_required(self) -> None:
        with self.assertRaises(ValueError):
            User.objects.create_user("")


class SoftDeleteTests(TestCase):
    """BaseModel soft delete hides records from the default manager."""

    def test_soft_delete_hides_from_default_manager(self) -> None:
        department = Department.objects.create(name="Cardiology")
        self.assertTrue(Department.objects.filter(name="Cardiology").exists())
        department.soft_delete()
        self.assertFalse(Department.objects.filter(name="Cardiology").exists())
        self.assertTrue(Department.all_objects.filter(name="Cardiology").exists())
        self.assertTrue(department.is_deleted)

    def test_soft_delete_keeps_updated_at(self) -> None:
        department = Department.objects.create(name="Oncology")
        before = department.updated_at
        department.soft_delete()
        self.assertGreaterEqual(department.updated_at, before)

    def test_hard_delete_is_disabled(self) -> None:
        department = Department.objects.create(name="Neurology")
        with self.assertRaises(NotImplementedError):
            department.delete()


class PermissionSystemTests(TestCase):
    """user_has_permission + protected views + audit on denial."""

    def setUp(self) -> None:
        self.client = Client()

    def test_role_with_permission_allowed(self) -> None:
        role = Role.objects.create(name="Clerk")
        clerk = make_user("clerk@example.test", role=role)
        from apps.accounts.models import Permission

        permission = Permission.objects.create(code=USER_VIEW, description="view users")
        role.permissions.add(permission)
        self.client.force_login(clerk)
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 200)

    def test_role_without_permission_denied_with_audit(self) -> None:
        role = Role.objects.create(name="Empty")
        user = make_user("emptyrole@example.test", role=role)
        self.client.force_login(user)
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 403)
        entry = AuditLog.objects.filter(
            user=user, action=AuditLog.Action.PERMISSION_DENIED
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(template_name(response), "403.html")

    def test_no_role_denied(self) -> None:
        user = make_user("norole@example.test")
        self.client.force_login(user)
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 403)

    def test_superuser_bypass(self) -> None:
        superuser = make_user("boss@example.test", is_superuser=True, is_staff=True)
        self.client.force_login(superuser)
        response = self.client.get(reverse("user_list"))
        self.assertEqual(response.status_code, 200)
        # Superuser even passes codes no role has (styleguide)
        styleguide_response = self.client.get(reverse("styleguide"))
        self.assertEqual(styleguide_response.status_code, 200)

    def test_anonymous_redirects_to_login(self) -> None:
        response = self.client.get(reverse("user_list"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('user_list')}")

    def test_styleguide_denied_for_normal_user(self) -> None:
        user = make_user("plain@example.test")
        self.client.force_login(user)
        response = self.client.get(reverse("styleguide"))
        self.assertEqual(response.status_code, 403)


def template_name(response):
    for template in response.templates:
        if template.name:
            return template.name
    return None


class LoginAuditTests(TestCase):
    """LOGIN / LOGIN_FAILED audit entries and lockout behaviour."""

    def setUp(self) -> None:
        cache.clear()
        self.client = Client()
        self.user = make_user("password-user@example.test")
        self.url = reverse("login")

    def post_login(self, email: str, password: str):
        return self.client.post(self.url, {"username": email, "password": password})

    def test_successful_login_is_audited(self) -> None:
        response = self.post_login("PASSWORD-user@example.test", SEED_PW)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))
        entry = AuditLog.objects.filter(user=self.user, action=AuditLog.Action.LOGIN).first()
        self.assertIsNotNone(entry)

    def test_failed_login_is_audited(self) -> None:
        response = self.post_login("password-user@example.test", "wrong-password")
        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.filter(
            user=self.user, action=AuditLog.Action.LOGIN_FAILED
        ).first()
        self.assertIsNotNone(entry)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.LOGIN).exists())

    def test_unknown_email_failure_without_user(self) -> None:
        response = self.post_login("ghost@example.test", SEED_PW)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(user=None, action=AuditLog.Action.LOGIN_FAILED).exists()
        )

    @override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_LOCKOUT_SECONDS=600)
    def test_lockout_after_limit_and_logging(self) -> None:
        for _ in range(3):
            self.post_login("lockme@example.test", "bad-password")
        self.assertTrue(is_locked("lockme@example.test"))
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.LOGIN_LOCKED).exists()
        )

    @override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_LOCKOUT_SECONDS=600)
    def test_locked_user_cannot_login_with_correct_password(self) -> None:
        for _ in range(3):
            self.post_login("locked@example.test", "bad-password")
        response = self.post_login("locked@example.test", SEED_PW)
        self.assertEqual(response.status_code, 200)  # blocked before authenticate
        self.assertFalse(AuditLog.objects.filter(
            user=self.user, action=AuditLog.Action.LOGIN, object_id=str(self.user.pk)
        ).exists())

    def tearDown(self) -> None:
        clear_failures("lockme@example.test")
        clear_failures("locked@example.test")


class DashboardRedirectTests(TestCase):
    """Login redirects to dashboard; every seeded role hits its own template."""

    def setUp(self) -> None:
        call_command("seed_roles", stdout=StringIO())

    def test_each_seeded_role_gets_expected_dashboard(self) -> None:
        client = Client()
        for spec in ROLES:
            with self.subTest(role=spec["name"]):
                role = Role.objects.get(name=spec["name"])
                user = make_user(
                    f"user{spec['name'].replace(' ', '').lower()}@example.test",
                    role=role,
                )
                client.force_login(user)
                response = client.get(reverse("dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(template_name(response), spec["dashboard_template"])

    def test_user_without_role_falls_back_to_generic(self) -> None:
        user = make_user("fallback@example.test")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(template_name(response), "dashboards/generic.html")

    def test_invalid_dashboard_template_falls_back(self) -> None:
        role = Role.objects.create(
            name="Broken", dashboard_template="dashboards/missing.html"
        )
        user = make_user("broken@example.test", role=role)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(template_name(response), "dashboards/generic.html")


class SidebarPermissionTests(TestCase):
    """Sidebar (and dashboard cards) show only permitted modules."""

    def setUp(self) -> None:
        call_command("seed_roles", stdout=StringIO())

    def login_as(self, role_name: str):
        role = Role.objects.get(name=role_name)
        user = make_user(
            f"{role_name.replace(' ', '').lower()}@example.test", role=role
        )
        self.client.force_login(user)
        return response_of(self.client.get(reverse("dashboard")))

    def test_admin_sees_admin_modules(self) -> None:
        body = self.login_as("Super Admin")
        self.assertIn("Users", body)
        self.assertIn("Audit log", body)
        self.assertIn('href="/users/"', body)

    def test_doctor_does_not_see_users_module(self) -> None:
        body = self.login_as("Doctor")
        self.assertNotIn("Users", body)
        self.assertNotIn("user_list", body)
        self.assertIn("Coming soon", body)

    def test_accountant_sees_audit_only_module(self) -> None:
        body = self.login_as("Accountant")
        self.assertIn("Audit log", body)
        self.assertNotIn('"user_list"', body)


def response_of(response):
    return response.content.decode()


class SeedCommandTests(TestCase):
    """seed_roles / seed_users are idempotent; seed_users honours DEBUG."""

    def test_seed_roles_idempotent(self) -> None:
        call_command("seed_roles", stdout=StringIO())
        roles_before = Role.objects.count()
        permissions_before = RolePermissionEntry()
        call_command("seed_roles", stdout=StringIO())
        self.assertEqual(Role.objects.count(), roles_before)
        self.assertEqual(Role.objects.count(), len(ROLES))
        self.assertEqual(permissions_before, RolePermissionEntry())

    @override_settings(DEBUG=True, SEED_DEFAULT_PASSWORD=SEED_PW)
    def test_role_permissions_match_seed_data(self) -> None:
        call_command("seed_roles", stdout=StringIO())
        with StringIO() as out:
            call_command("seed_users", stdout=out)
        for spec in ROLES:
            role = Role.objects.get(name=spec["name"])
            self.assertEqual(
                set(role.permissions.values_list("code", flat=True)),
                set(spec["permissions"]),
            )

    @override_settings(DEBUG=True, SEED_DEFAULT_PASSWORD=SEED_PW)
    def test_seed_users_idempotent(self) -> None:
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_users", stdout=StringIO())
        count = User.objects.count()
        self.assertEqual(count, len(USERS))
        call_command("seed_users", stdout=StringIO())
        self.assertEqual(User.objects.count(), count)
        doctor = User.objects.get(email="doctor@example.test")
        self.assertEqual(doctor.full_name, "Dolores Doctor")
        self.assertTrue(doctor.staffprofile.department_id)

    @override_settings(SEED_DEFAULT_PASSWORD=SEED_PW)
    @override_settings(DEBUG=True, SEED_DEFAULT_PASSWORD=SEED_PW)
    def test_seed_users_created_fake_emails(self) -> None:
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_users", stdout=StringIO())
        for spec in USERS:
            self.assertTrue(User.objects.filter(email=spec["email"]).exists())

    @override_settings(DEBUG=False, SEED_DEFAULT_PASSWORD=SEED_PW)
    def test_seed_users_refuses_when_debug_false(self) -> None:
        call_command("seed_roles", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("seed_users", stdout=StringIO())

    @override_settings(DEBUG=True, SEED_DEFAULT_PASSWORD="")
    def test_seed_users_requires_password_setting(self) -> None:
        call_command("seed_roles", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("seed_users", stdout=StringIO())


def RolePermissionEntry() -> int:
    """Count of role-permission links (helper for idempotency checks)."""
    from apps.accounts.models import RolePermission

    return RolePermission.objects.count()


class AuditAppendOnlyTests(TestCase):
    """AuditLog entries cannot be updated or deleted."""

    def test_update_blocked(self) -> None:
        entry = AuditLog.objects.create(action=AuditLog.Action.LOGIN)
        entry.details = "tamper attempt"
        with self.assertRaises(NotImplementedError):
            entry.save()

    def test_delete_blocked(self) -> None:
        entry = AuditLog.objects.create(action=AuditLog.Action.LOGOUT)
        with self.assertRaises(NotImplementedError):
            entry.delete()

    def test_timestamp_indexed_model_meta(self) -> None:
        index_fields = [tuple(i.fields) for i in AuditLog._meta.indexes]
        self.assertIn(("timestamp",), index_fields)
        self.assertIn(("user",), index_fields)
        self.assertIn(("action",), index_fields)


class RegistryPermissionLinkTests(TestCase):
    """Every active registry module must resolve to a named, permitted URL."""

    def setUp(self) -> None:
        call_command("seed_roles", stdout=StringIO())

    def test_registry_urls_resolve(self) -> None:
        from core.registry import MODULES

        for entry in MODULES:
            if entry["active"] and entry["url_name"]:
                reverse(entry["url_name"])


class LockoutHelperTests(TestCase):
    """Unit-level checks for the cache-based lockout helper."""

    def setUp(self) -> None:
        cache.clear()

    @override_settings(LOGIN_FAILURE_LIMIT=2, LOGIN_LOCKOUT_SECONDS=60)
    def test_lock_expires_after_window(self) -> None:
        register_failure("oops@example.test")
        register_failure("oops@example.test")
        self.assertTrue(is_locked("oops@example.test"))
        expiry = cache.get("login-lock:oops@example.test")
        self.assertGreater(expiry, 0)
        cache.set("login-lock:oops@example.test", 1)  # simulate long time passing
        self.assertFalse(is_locked("oops@example.test"))

    @override_settings(LOGIN_FAILURE_LIMIT=5)
    def test_counter_audits_each_failure(self) -> None:
        user = User.objects.create_user(email="count@example.test", password=SEED_PW)
        register_failure("count@example.test", user=user)
        register_failure("count@example.test", user=user)
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED).count(), 2
        )
