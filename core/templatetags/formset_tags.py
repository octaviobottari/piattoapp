# core/templatetags/formset_tags.py
from django import template

register = template.Library()

@register.filter
def lookup(dictionary, key):
    return dictionary.get(key)

@register.filter
def attr(obj, attribute):
    return getattr(obj, attribute)