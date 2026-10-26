"""Cache-based login rate limiting: fail counter with lockout.

Limits and lockout duration come from settings (LOGIN_FAILURE_LIMIT,
LOGIN_LOCKOUT_SECONDS). Lockout creation is written to the AuditLog.
"""
import time

from django.conf import settings
from django.core.cache import cache

from apps.audit.models import AuditLog
from apps.audit.utils import log_to_audit

_FAIL_PREFIX = "login-fail:"
_LOCK_PREFIX = "login-lock:"


def _fail_key(identifier: str) -> str:
    return f"{_FAIL_PREFIX}{identifier}"


def _lock_key(identifier: str) -> str:
    return f"{_LOCK_PREFIX}{identifier}"


def is_locked(identifier: str) -> bool:
    """True while the identifier is under an active lockout window."""
    expiry = cache.get(_lock_key(identifier))
    return bool(expiry and expiry >= time.time())


def register_failure(identifier: str, *, user=None, request=None) -> bool:
    """Record one failed attempt; create the lockout at the limit.

    Returns True when this failure just triggered the lockout.
    """
    key = _fail_key(identifier)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)
        count = 1
    log_to_audit(
        user=user,
        action=AuditLog.Action.LOGIN_FAILED,
        request=request,
        object_type="user",
        object_id=identifier,
        details=f"Failed attempt {count}/{settings.LOGIN_FAILURE_LIMIT}",
    )
    if count >= settings.LOGIN_FAILURE_LIMIT:
        cache.set(_lock_key(identifier), time.time() + settings.LOGIN_LOCKOUT_SECONDS,
                  settings.LOGIN_LOCKOUT_SECONDS)
        log_to_audit(
            user=user,
            action=AuditLog.Action.LOGIN_LOCKED,
            request=request,
            object_type="user",
            object_id=identifier,
            details=f"Locked for {settings.LOGIN_LOCKOUT_SECONDS}s after {count} failures",
        )
        cache.delete(key)
        return True
    return False


def clear_failures(identifier: str) -> None:
    """Reset the counter after a successful login."""
    cache.delete(_fail_key(identifier))
    cache.delete(_lock_key(identifier))
