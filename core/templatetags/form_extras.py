# core/templatetags/form_extras.py
from django import template
from django.forms import BoundField

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    # Check if the field is a form field, not a string or another type
    if isinstance(field, BoundField):
        return field.as_widget(attrs={"class": css_class})
    return field  # If it's a string or other type, return it unchanged
