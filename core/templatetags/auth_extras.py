from django import template

register = template.Library()

@register.filter
def get_model_name(user):
    if hasattr(user, '_meta'):
        return user._meta.model_name
    return ''