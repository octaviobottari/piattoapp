from django import template

register = template.Library()

@register.filter
def replace_comma(value):
    if value is None:
        return "0.00"
    if isinstance(value, (int, float)):
        return str(value).replace(',', '.')
    return str(value).replace(',', '.')