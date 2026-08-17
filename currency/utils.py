from .models import Currency

SESSION_KEY = 'display_currency_code'


def get_active_currency(request):
    """Resolves the visitor's chosen display currency from the session,
    falling back to the base currency, and falling back again to a
    synthetic identity currency if no Currency rows exist at all yet
    (fresh install with an empty currency table shouldn't break price
    display — it should just show amounts unconverted)."""
    code = request.session.get(SESSION_KEY)
    if code:
        currency = Currency.objects.filter(code=code).first()
        if currency:
            return currency

    base = Currency.get_base()
    if base:
        return base

    return Currency(code='INR', name='Indian Rupee', symbol='₹', rate_to_base=1, is_base=True)
