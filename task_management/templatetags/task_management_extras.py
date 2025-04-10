from django import template
from urllib.parse import quote


register = template.Library()

@register.filter
def add_class(value, arg):
    try:
        return value.as_widget(attrs={'class': arg})
    except AttributeError:
        return value  # Return the value unchanged if it doesn't have as_widget
    
@register.filter(name='quote')
def url_quote(value):
    return quote(value)