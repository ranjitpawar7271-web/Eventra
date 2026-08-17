from django import template

from currency.utils import get_active_currency

register = template.Library()


@register.simple_tag(takes_context=True)
def display_price(context, base_amount):
    """Renders a base-currency (INR) amount converted into the visitor's
    chosen display currency, e.g. {% display_price event.price %}. The
    underlying value passed in is always INR — this only changes how
    it's shown. See currency.models.Currency for the scope of that
    distinction."""
    request = context.get('request')
    if request is None:
        return base_amount
    currency = get_active_currency(request)
    converted = currency.convert_from_base(base_amount)
    return f"{currency.symbol}{converted}"
