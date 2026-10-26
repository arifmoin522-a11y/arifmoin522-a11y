"""Helpers for writing audit entries and resolving client IPs."""
from typing import Any, Optional

from django.http import HttpRequest

from .models import AuditLog

PROXY_HEADER = "HTTP_X_FORWARDED_FOR"


def get_client_ip(request: HttpRequest) -> Optional[str]:
    """Best-effort client IP: proxy chain first, then REMOTE_ADDR."""
    forwarded = request.META.get(PROXY_HEADER)
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def log_to_audit(
    *,
    user: Any = None,
    action: str,
    request: "HttpRequest | None" = None,
    object_type: str = "",
    object_id: str | int = "",
    details: str = "",
) -> AuditLog:
    """Create one immutable AuditLog entry and return it."""
    ip = None
    if request is not None:
        ip = getattr(request, "client_ip", None) or get_client_ip(request)
    return AuditLog.objects.create(
        user=user,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id not in ("", None) else "",
        details=details,
        ip_address=ip,
    )
