"""Middleware that resolves the client IP once per request for audit use."""
from typing import Callable

from django.http import HttpRequest, HttpResponse

from .utils import get_client_ip


class AuditContextMiddleware:
    """Sets ``request.client_ip`` for consistent audit logging."""

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.client_ip = get_client_ip(request)
        return self.get_response(request)
