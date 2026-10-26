# Hospital ERP — Phase 1

Django-based hospital management system. **Phase 1** delivers the shared
foundation: email-based authentication with lockout, role-based access
control (RBAC), user/staff/department management with soft deletes, a
per-role dashboard, and an append-only audit trail — all behind a custom
monochrome design system.

Clinical modules (patients, appointments, admissions, pharmacy, billing) are
registered as permissions and appear on dashboards as disabled placeholders;
they are not implemented yet — see
[Adding a module beyond Phase 1](#adding-a-module-beyond-phase-1).

## Table of contents

- [Stack](#stack)
- [Project layout](#project-layout)
- [Quick start (development)](#quick-start-development)
- [Environment variables](#environment-variables)
- [Seeded data](#seeded-data)
- [Roles and permissions](#roles-and-permissions)
- [URL map](#url-map)
- [Security behaviour](#security-behaviour)
- [Audit trail](#audit-trail)
- [Architecture rules](#architecture-rules)
- [Tests](#tests)
- [Running in production](#running-in-production)
- [Troubleshooting](#troubleshooting)
- [Adding a module beyond Phase 1](#adding-a-module-beyond-phase-1)

## Stack

| Layer      | Choice                                       |
| ---------- | -------------------------------------------- |
| Runtime    | Python 3.11                                  |
| Framework  | Django 5.2                                   |
| Database   | SQLite (dev), PostgreSQL (prod, via env)     |
| Config     | django-environ (12-factor .env files)        |
| Passwords  | argon2-cffi (Argon2id)                       |
| Front-end  | No frameworks — token-based CSS design system (`static/css/tokens.css`) + vanilla JS (`theme.js`, `sidebar.js`, `halftone.js`) + inline SVG icon sprite |
| Icons      | Inline SVG sprite in `templates/components/icons.html`, rendered by the `{% icon "name" %}` tag |

## Project layout

```
config/                 Project package; settings split base/dev/prod
config/settings/base.py Everything shared; reads the environment only
config/settings/dev.py  Dev-only fallbacks (random SECRET_KEY, SQLite)
config/settings/prod.py Production hardening
core/                   Shared app (not URL-facing except styleguide)
core/models.py          BaseModel with created/updated/is_deleted + soft delete
core/permissions.py     THE permission constant registry (single source)
core/registry.py        Module registry: sidebar entries + dashboard cards
core/decorators.py      permission_required_code + PermissionRequiredMixin
core/context_processors.py  nav_modules / dashboard_cards for all templates
core/templatetags/core_tags.py  {% icon %} and related template tags
apps/accounts/          User (email login), Role, StaffProfile, Department,
                        login lockout, seed_data + seed management commands
apps/audit/             Append-only AuditLog, logging utils, middleware
templates/              base.html, auth/, dashboards/, users/, roles/,
                        departments/, audit/, styleguide, errors, components/
static/                 css/{tokens,base,components,layout}.css, js/*.js
requirements.txt        Pinned runtime dependencies
.env.example            Copy to .env and adjust for your machine
```

## Quick start (development)

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set SECRET_KEY etc.
venv/bin/python manage.py migrate
venv/bin/python manage.py seed_roles      # creates permissions, roles, departments
venv/bin/python manage.py seed_users      # demo staff per role (DEBUG builds only)
venv/bin/python manage.py runserver
```

Then open `http://127.0.0.1:8000/login/` and sign in as
`admin@example.test` with the seeded password.

Both seed commands are idempotent — safe to re-run. `seed_users`
**refuses to run when `DEBUG=False`** and requires `SEED_DEFAULT_PASSWORD`
in the environment, so demo credentials can never leak into production.

For a real administrator instead of demo data:

```bash
venv/bin/python manage.py createsuperuser   # email login, full permission bypass
```

## Environment variables

All configuration is environment-driven; nothing is hardcoded in the app.

| Variable               | Default / format         | Purpose                                        |
| ---------------------- | ------------------------ | ---------------------------------------------- |
| `SECRET_KEY`           | random fallback in dev   | Django cryptographic secret (required in prod) |
| `DEBUG`                | `False`                  | `True` only for development                    |
| `ALLOWED_HOSTS`        | `127.0.0.1,localhost`    | comma-separated hosts                          |
| `DB_BACKEND`           | `sqlite`                 | `sqlite` or `postgres`                         |
| `DB_NAME`              | `hospital_erp.sqlite3`   | database name (file for SQLite)                |
| `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | — | PostgreSQL connection settings     |
| `SEED_DEFAULT_PASSWORD`| —                        | password given to seeded demo users            |
| `SESSION_IDLE_TIMEOUT` | `1800` s                 | seconds of inactivity before session expiry    |
| `LOGIN_FAILURE_LIMIT`  | `5`                      | failed attempts before the email is locked     |
| `LOGIN_LOCKOUT_SECONDS`| `300` s                  | how long a locked email stays locked           |
| `MAX_DASHBOARD_CARDS`  | `5`                      | max cards rendered on any dashboard            |

## Seeded data

`apps/accounts/seed_data.py` is the single source of truth for every seeded
record. Demo emails are fake on purpose (`<name>@example.test`):

| Account                        | Role           | Superuser |
| ------------------------------ | -------------- | --------- |
| `admin@example.test`           | Super Admin    | yes       |
| `doctor@example.test`          | Doctor         | no        |
| `nurse@example.test`           | Nurse          | no        |
| `reception@example.test`       | Receptionist   | no        |
| `pharmacist@example.test`      | Pharmacist     | no        |
| `lab@example.test`             | Lab Technician | no        |
| `accountant@example.test`      | Accountant     | no        |

Seeded departments: Emergency, Internal Medicine, Pediatrics, Radiology,
Administration.

## Roles and permissions

Access checks use permission **codes**, never role names. Every code lives
in `core/permissions.py` (and nowhere else); views bind to codes with
`permission_required_code(code)` / `PermissionRequiredMixin`, and templates
test codes like `{% if "user.view" in user_permissions %}`.

| Role           | Dashboard template         | Permission codes                                      |
| -------------- | -------------------------- | ----------------------------------------------------- |
| Super Admin    | `dashboards/admin.html`    | all codes (plus superuser bypass in the helper)       |
| Doctor         | `dashboards/clinical.html` | `department.view`, `staff.view`                       |
| Nurse          | `dashboards/clinical.html` | `staff.view`                                          |
| Receptionist   | `dashboards/reception.html`| `department.view`                                     |
| Pharmacist     | `dashboards/pharmacy.html` | —                                                     |
| Lab Technician | `dashboards/lab.html`      | —                                                     |
| Accountant     | `dashboards/finance.html`  | `audit.view`, `department.view`                       |

Full code list: `user.view/create/edit/delete`, `role.view/create/edit/
delete`, `department.view/edit`, `staff.view/edit`, `audit.view`,
`styleguide.view` (superusers only).

Each dashboard template renders whatever cards the user's permissions
admit, capped by `MAX_DASHBOARD_CARDS`; templates come from the
`dashboard_template` field stored on `Role` — adding a new role requires no
template change if you reuse an existing dashboard.

## URL map

All routes live in `apps/accounts/urls.py`:

| URL                      | Name             | Protection (permission code)      |
| ------------------------ | ---------------- | --------------------------------- |
| `/`                      | `dashboard`      | login required (per-role template)|
| `/login/`                | `login`          | public, rate-limited by lockout   |
| `/logout/`               | `logout`         | POST only                         |
| `/users/` …              | `user_*`         | `user.view/create/edit/delete`    |
| `/staff/`, `/staff/<pk>/`| `staff_list/detail` | `staff.view`                   |
| `/roles/` …              | `role_*`         | `role.view/create/edit/delete`    |
| `/departments/` …        | `department_*`   | `department.view` / `.edit`       |
| `/audit/`                | `audit_list`     | `audit.view`                      |
| `/styleguide/`           | `styleguide`     | superuser only                    |

User and role deletes are **soft** (`is_deleted=True`); the `ActiveManager`
hides deleted rows everywhere, including Django admin.

## Security behaviour

- **Login** is email + password. Every failure (`LOGIN_FAILED`), every
  lock (`LOGIN_LOCKED`) and every success (`LOGIN`) is audit-logged, with
  IP and reason.
- **Lockout**: after `LOGIN_FAILURE_LIMIT` failures for one email, that
  email is refused even with the correct password until
  `LOGIN_LOCKOUT_SECONDS` pass (cache-based, per email, reset on success).
- **Sessions** idle-expire after `SESSION_IDLE_TIMEOUT`
  (`SESSION_COOKIE_AGE` + `SESSION_SAVE_EVERY_REQUEST=True`); `prod.py`
  enables `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPOnly` and HTTPS
  redirects.
- **Anonymous** visitors are redirected to `/login/`; authenticated
  visitors missing a permission get the 403 page plus a `PERMISSION_DENIED`
  audit entry.
- **Audit log is append-only**: updating or deleting an `AuditLog` raises
  (`apps/audit/models.py`), including from Django admin.

## Audit trail

Every record carries actor, action, object type + id + repr, reason,
change note, and client IP, captured via `AuditContextMiddleware`
(`request.client_ip`) and `apps/audit/utils.log_to_audit`. Current actions:
`LOGIN`, `LOGOUT`, `LOGIN_FAILED`, `LOGIN_LOCKED`, `CREATE`, `UPDATE`,
`DELETE`, `PERMISSION_DENIED`.

## Architecture rules

1. **One permission vocabulary** — codes only in `core/permissions.py`;
   everything else imports, never redefining.
2. **No role-name routing** — behaviour reacts to permission codes only;
   roles are data, never `if role.name`.
3. **Dashboard routing is data** — `Role.dashboard_template`, with a safe
   generic fallback when a template is missing.
4. **Navigation is derived** — sidebar and cards come from
   `core/registry.py` filtered by permissions; register once, get nav + dashboards automatically.
5. **Settings are environment-only** — no secrets, DB URLs, or flags in
   code; `dev.py` may only add *fallbacks*.
6. **Seeding is idempotent + guarded** — `get_or_create` everywhere;
   demo seeding blocked when `DEBUG=False`.
7. **Explicit fail-closed** — unknown permission codes deny, missing
   dashboards fall back, unknown login attempts are logged.

## Tests

```bash
venv/bin/python manage.py test     # 37 tests
```

Coverage: user manager + email normalisation, soft delete + managers,
permission allow/deny/superuser bypass, login success/failure/lockout
auditing, per-role dashboard routing, sidebar filtering, seed idempotency
and the DEBUG guard, audit append-only, registry URL wiring, lockout helper
units, and case-insensitive email login.

## Running in production

```bash
export DEBUG=False
export SECRET_KEY=<64+ random chars>
export ALLOWED_HOSTS=erp.example.org
export DB_BACKEND=postgres DB_NAME=... DB_USER=... DB_PASSWORD=... DB_HOST=... DB_PORT=5432
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
gunicorn config.wsgi --bind 0.0.0.0:8000
```

Never run `seed_users` on production (`DEBUG=False` blocks it by design);
create real staff via `/users/add/` as Super Admin or `createsuperuser`.

## Troubleshooting

| Symptom                                       | Cause / fix                                            |
| --------------------------------------------- | ------------------------------------------------------ |
| `seed_users` says "only runs when DEBUG=True" | set `DEBUG=True` + `SEED_DEFAULT_PASSWORD`, re-run     |
| Locked out during testing                     | clear cache (`python -c "…cache.clear()…"`) or wait `LOGIN_LOCKOUT_SECONDS` |
| `/styleguide/` 403                            | intentionally superuser-only (see `core/permissions.py`) |
| Wrong dashboard for a role                    | check `Role.dashboard_template`; fallback is `dashboards/generic.html` |

## Adding a module beyond Phase 1

1. Add the permission codes in `core/permissions.py`
   (and `PERMISSION_DESCRIPTIONS` so seed roles can pick them up).
2. Register the module in `core/registry.py` (name, URL name, icon,
   dashboard-card flag) — the sidebar, dashboards and seed role output
   derive from the registry automatically.
3. Grant the new `*_view` code to roles in `apps/accounts/seed_data.py`
   and re-run `venv/bin/python manage.py seed_roles`.
4. Write the URL + view + templates; decorate with the new permission
   codes. No nav or dashboard edits are needed.

---

© 2026 arifmoin522-a11y — Hospital ERP. All rights reserved.
