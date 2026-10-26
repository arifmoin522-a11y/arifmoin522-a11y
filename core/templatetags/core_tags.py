"""Template tags for the icon system used across templates."""
from django import template
from django.template.loader import render_to_string

register = template.Library()


@register.simple_tag(name="icon")
def icon(name: str) -> str:
    """Render an inline outline icon; name matches a sprite symbol id."""
    return render_to_string("components/icon.html", {"name": name})
