from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key], or None if missing or not a dict."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)
