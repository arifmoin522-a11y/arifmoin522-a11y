"""Patient phone masking in templates.

Same algorithm as apps.patients.models.mask_phone, applied in list and
history rows depending on ``show_contact`` context.
"""
from django import template

register = template.Library()


@register.filter
def mask(value: str) -> str:
    """Keep only the last 3 digits visible."""
    if not value:
        return "—"
    return "*" * max(len(value) - 3, 0) + value[-3:]
