from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Replaces all occurrences of the first part of arg with the second part in value.
    Usage: {{ string|replace:"old,new" }}
    """
    try:
        old, new = arg.split(',', 1)
        return str(value).replace(old, new)
    except ValueError:
        return value

@register.filter
def div(value, arg):
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def argentine_format(value):
    """
    Formats a number to Argentine format (e.g., 11000.00 -> 11000,00) without thousand separators.
    """
    try:
        # Convert to Decimal for precise handling
        if isinstance(value, str):
            value = Decimal(value.replace(',', '.'))
        else:
            value = Decimal(str(value))
        # Format with 2 decimal places, replace period with comma
        formatted = f"{value:.2f}".replace('.', ',')
        return formatted
    except (ValueError, TypeError, InvalidOperation):
        return '0,00'