from django import template

register = template.Library()


@register.filter
def vnd(value):
    """159000 -> 159.000 (dấu chấm ngăn cách hàng nghìn, kiểu Việt Nam)."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return value


@register.filter
def get_item(mapping, key):
    """Lấy mapping[key] trong template, không có thì trả về 0."""
    try:
        return mapping.get(key, 0)
    except AttributeError:
        return 0
    