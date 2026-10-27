"""Shared Django settings for the hospital ERP.

Everything environment-specific comes from env vars. Deployment settings
modules (dev.py / prod.py) select DEBUG behaviour and security flags.
"""
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


def _required_env(name: str) -> str:
    """Return an env var value or raise a clear error when it is missing."""
    value = env(name, default="")
    if not value:
        raise ImproperlyConfigured(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and set it."
        )
    return value


# SECURITY
SECRET_KEY = env.str("SECRET_KEY", default="")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = [
    h.strip()
    for h in env.str("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")
    if h.strip()
]

# APPLICATIONS
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]
THIRD_PARTY_APPS: list[str] = []
LOCAL_APPS = [
    "core",
    "apps.accounts",
    "apps.audit",
    "apps.patients",
    "apps.appointments",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
            ],
        },
    },
]

# DATABASE (env-driven; sqlite for dev, postgres by changing .env only)
DB_BACKEND = env.str("DB_BACKEND", default="sqlite")
if DB_BACKEND == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / env.str("DB_NAME", default="db.sqlite3"),
        }
    }
elif DB_BACKEND == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env.str("DB_NAME"),
            "USER": env.str("DB_USER"),
            "PASSWORD": env.str("DB_PASSWORD"),
            "HOST": env.str("DB_HOST", default="localhost"),
            "PORT": env.str("DB_PORT", default="5432"),
        }
    }
else:
    raise ImproperlyConfigured(
        f"Unsupported DB_BACKEND '{DB_BACKEND}'. Use 'sqlite' or 'postgres'."
    )

# PASSWORDS
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# LOGIN / SECURITY BEHAVIOUR (all env-overridable)
SEED_DEFAULT_PASSWORD = env.str("SEED_DEFAULT_PASSWORD", default="")
SESSION_COOKIE_AGE = env.int("SESSION_IDLE_TIMEOUT", default=1800)
SESSION_SAVE_EVERY_REQUEST = True  # refresh age on activity => expiry on inactivity
LOGIN_FAILURE_LIMIT = env.int("LOGIN_FAILURE_LIMIT", default=5)
LOGIN_LOCKOUT_SECONDS = env.int("LOGIN_LOCKOUT_SECONDS", default=300)
MAX_DASHBOARD_CARDS = env.int("MAX_DASHBOARD_CARDS", default=8)
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# FRONT DESK (Phase 2) — code generation, forms, booking and display tuning
TIME_ZONE = env.str("TIME_ZONE", default="UTC")
PATIENT_CODE_PREFIX = env.str("PATIENT_CODE_PREFIX", default="PAT")
APPOINTMENT_CODE_PREFIX = env.str("APPOINTMENT_CODE_PREFIX", default="APT")
CODE_SEQUENCE_DIGITS = env.int("CODE_SEQUENCE_DIGITS", default=6)
CODE_SEQUENCE_START = env.int("CODE_SEQUENCE_START", default=1)
PHONE_REGEX = env.str("PHONE_REGEX", default=r"^\+?[0-9][0-9\- ]{6,19}$")
PAGE_SIZE = env.int("PAGE_SIZE", default=15)
APPOINTMENT_SLOT_MINUTES = env.int("APPOINTMENT_SLOT_MINUTES", default=30)
APPOINTMENT_CANCELLATION_WINDOW_MINUTES = env.int(
    "APPOINTMENT_CANCELLATION_WINDOW_MINUTES", default=120
)

X_FRAME_OPTIONS = "DENY"

# I18N
LANGUAGE_CODE = "en-us"
USE_I18N = True
USE_TZ = True

# STATIC
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
WSGI_APPLICATION = "config.wsgi.application"
ROOT_URLCONF = "config.urls"
