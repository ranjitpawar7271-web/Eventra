from django import template

register = template.Library()


@register.filter(name='add_class')
def add_class(field, css_class):
    """Add a CSS class to a form field's widget (useful for Django's built-in auth forms)."""
    return field.as_widget(attrs={'class': css_class, 'placeholder': field.label})
