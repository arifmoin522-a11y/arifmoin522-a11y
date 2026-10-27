"""Backend permission enforcement: function decorator and CBV mixin.

Both redirect anonymous users to login, return HTTP 403 (custom template)
when the permission is missing, and write a PERMISSION_DENIED AuditLog
entry. Missing permissions are a backend concern; the sidebar is only a
convenience.
"""
import functools
from typing import Any, Callable

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from apps.audit.models import AuditLog
from apps.audit.utils import log_to_audit
from core.permissions import user_has_permission


class LoginNeeded(Exception):  # noqa: N818 - private control-flow signal
    """Raised internally to trigger the login redirect."""


def _require(request: HttpRequest, code: str | None) -> None:
    """Shared guard: login redirect, permission check, audit on denial."""
    if not request.user.is_authenticated:
        raise LoginNeeded(request)
    if code is not None and not user_has_permission(request.user, code, request=request):
        log_to_audit(
            user=request.user,
            action=AuditLog.Action.PERMISSION_DENIED,
            request=request,
            object_type="view",
            object_id=request.path,
            details=f"Missing permission: {code}",
        )
        raise PermissionDenied


def permission_required_code(code: str) -> Callable:
    """Function-view decorator enforcing a permission code."""

    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            from django.contrib.auth.views import redirect_to_login

            try:
                _require(request, code)
            except LoginNeeded:
                return redirect_to_login(request.get_full_path())
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def permission_required_any(*codes: str) -> Callable:
    """Function-view decorator enforcing ANY of the given permission codes."""

    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            from django.contrib.auth.views import redirect_to_login

            try:
                if not request.user.is_authenticated:
                    raise LoginNeeded(request)
                if not any(
                    user_has_permission(request.user, code, request=request)
                    for code in codes
                ):
                    log_to_audit(
                        user=request.user,
                        action=AuditLog.Action.PERMISSION_DENIED,
                        request=request,
                        object_type="view",
                        object_id=request.path,
                        details=f"Missing permission: any of {', '.join(codes)}",
                    )
                    raise PermissionDenied
            except LoginNeeded:
                return redirect_to_login(request.get_full_path())
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class PermissionRequiredMixin:
    """Class-based-view mixin enforcing ``permission_code``."""

    permission_code: str | None = None

    def get_permission_code(self) -> str | None:
        """Hook so subclasses can compute the required code dynamically."""
        return self.permission_code

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from django.contrib.auth.views import redirect_to_login

        try:
            _require(request, self.get_permission_code())
        except LoginNeeded:
            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]
