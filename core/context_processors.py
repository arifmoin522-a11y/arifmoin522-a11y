"""Context processors for the dynamically generated navigation."""
from typing import Any

from django.conf import settings
from django.http import HttpRequest


def navigation(request: HttpRequest) -> dict[str, Any]:
    """Expose permitted sidebar entries and dashboard cards to templates."""
    from core.registry import permitted_modules  # imported lazily

    is_authenticated = getattr(request, "user", None) is not None and (
        request.user.is_authenticated
    )
    modules = permitted_modules(request.user, request=request) if is_authenticated else []
    cards = [m for m in modules if m["in_dashboard"]]
    return {
        "nav_modules": [m for m in modules if m["in_nav"]],
        "dashboard_cards": cards[: settings.MAX_DASHBOARD_CARDS],
        "can_search_users": any(m["key"] == "users" for m in modules),
    }
