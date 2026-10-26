"""Development settings: permissive defaults suitable only for local dev."""
from .base import *  # noqa: F401,F403

# A random per-process key so no secret is ever hardcoated; set SECRET_KEY in
# .env for a stable value across restarts.
from django.utils.crypto import get_random_string  # noqa: E402

SECRET_KEY = SECRET_KEY or get_random_string(64)
DEBUG = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
