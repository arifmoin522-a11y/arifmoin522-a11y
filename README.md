# Hospital ERP (Phase 1)

Django-based hospital management system, Phase 1: authentication, role-based
access control, staff/user management, departments, and an append-only audit
trail. Phase 1 deliberately stops at the shared foundation; clinical modules
(patients, appointments, admissions, pharmacy, billing) are registered as
permissions and appear as placeholders but are not yet implemented.

## Stack

- Python 3.11, Django 5.2
- SQLite in development (PostgreSQL supported via environment variables)
- django-environ for configuration, argon2-cffi for password hashing
- No third-party CSS/JS frameworks: monochrome token-based design system
  (`static/css/tokens.css`), vanilla JS (`static/js/theme.js`, `sidebar.js`,
  `halftone.js`), inline SVG icon sprite.

## Project layout

```
config/            project root, settings/base.py + dev.py + prod.py
core/              shared app: BaseModel, permissions, decorators, module
                   registry, context processors, template tags, styleguide
apps/accounts/     User (email login), Role, StaffProfile, Department,
                   lockout, seed commands
apps/audit/        append-only AuditLog, util + middleware
templates/         base layout, dashboards, CRUD views, static pages
static/            design-system CSS and vanilla JS
```

## Quick start (development)

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit SECRET_KEY etc.
venv/bin/python manage.py migrate
venv/bin/python manage.py seed_roles      # creates roles + permissions
venv/bin/python manage.py seed_users      # demo staff per role (DEBUG only)
venv/bin/python manage.py runserver
```

`seed_users` refuses to run when `DEBUG=False` and requires
`SEED_DEFAULT_PASSWORD` from the environment. Demo accounts use
`<role>@example.test` fake emails (e.g. `doctor@example.test`); set their
password with `SEED_DEFAULT_PASSWORD` before seeding.

For a real administrator instead of demo data:

```bash
python manage.py createsuperuser   # email login, full permission bypass
```

## Environment variables

| Variable                | Purpose                                        |
| ----------------------- | ---------------------------------------------- |
| `SECRET_KEY`            | Django secret; required in production          |
| `DEBUG`                 | `True` only for development                    |
| `ALLOWED_HOSTS`         | comma-separated hosts                          |
| `DB_BACKEND`            | `sqlite` (default) or `postgres`               |
| `DB_NAME/USER/PASSWORD/HOST/PORT` | PostgreSQL connection settings       |
| `SEED_DEFAULT_PASSWORD` | password for seeded demo users                 |
| `SESSION_IDLE_TIMEOUT`  | seconds of inactivity before session expiry    |
| `LOGIN_FAILURE_LIMIT`   | failed attempts before lockout (default 5)     |
| `LOGIN_LOCKOUT_SECONDS` | lockout duration (default 300)                 |
| `MAX_DASHBOARD_CARDS`   | max cards rendered on any dashboard (default 5)|

## Roles and permissions

Log in with any seeded account and the dashboard, sidebar and action buttons
come from the module registry (`core/registry.py`) filtered by the user's
permissions — never from role-name checks. Permission constants live only in
`core/permissions.py`; templates use the codes through
`{% if "user.view" in user_permissions %}`-style checks or the
`user_has_permission` helper.

| Role            | Dashboard             | Can                                              |
| --------------- | --------------------- | ------------------------------------------------ |
| Super Admin     | `dashboards/admin.html`     | everything incl. users, roles, audit, styleguide |
| Doctor          | `dashboards/clinical.html`  | departments view/edit                            |
| Nurse           | `dashboards/clinical.html`  | departments view/edit                            |
| Receptionist    | `dashboards/reception.html` | department/staff view                            |
| Pharmacist      | `dashboards/pharmacy.html`  | departments view                                 |
| Lab Technician  | `dashboards/lab.html`       | departments view                                 |
| Accountant      | `dashboards/finance.html`   | audit view                                       |

Full permission-check rules (case-sensitive via permission *codes*):
`manage.py seed_roles` prints what each role carries; the source of truth is
`apps/accounts/seed_data.py`.

## Security behaviour

- Login with email + password; unknown/failure attempts and lockouts are
  audit-logged. After `LOGIN_FAILURE_LIMIT` failures the email is locked for
  `LOGIN_LOCKOUT_SECONDS`.
- Sessions idle-expire after `SESSION_IDLE_TIMEOUT` seconds and are
  `SESSION_COOKIE_SECURE`-capable in `config/settings/prod.py`.
- Anonymous users are redirected to the login page; logged-in users without
  a required permission get the 403 page and a PERMISSION_DENIED audit entry.
- Audit records cannot be edited or deleted (model forbids both) and every
  entry stores actor, action, object, reason, and client IP.

## Tests

```bash
venv/bin/python manage.py test
```

Covers: user manager/normalisation, soft delete, permission allow/deny/
superuser bypass, login success/failure/lockout auditing, per-role dashboard
routing, sidebar filtering, seed idempotency and the DEBUG guard, audit
append-only guarantee, registry URL wiring, and lockout helpers.

## Adding a module beyond Phase 1

1. Add the permission codes in `core/permissions.py`
   (`PERMISSION_DESCRIPTIONS` too so seed roles can pick them up).
2. Register the module in `core/registry.py` (name, url name, icon,
   dashboard card flag) — the sidebar, dashboards and seed checklists derive
   from this registry automatically.
3. Grant the new `*_view` code to roles in `apps/accounts/seed_data.py` and
   re-run `python manage.py seed_roles`.
