"""Production settings: strict, fail-loud configuration."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY is not set. In production this must come from the "
        "environment. The application refuses to start without it."
    )

DEBUG = False
ALLOWED_HOSTS = ALLOWED_HOSTS or []
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS is empty in production. Set it in the environment."
    )

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

CACHES = {
    "default": {
        "BACKEND": env.str(
            "CACHE_BACKEND", default="django.core.cache.backends.locmem.LocMemCache"
        ),
    }
}
