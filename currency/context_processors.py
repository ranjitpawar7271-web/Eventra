from .models import Currency
from .utils import get_active_currency


def active_currency(request):
    return {
        'active_currency': get_active_currency(request),
        'available_currencies': Currency.objects.all(),
    }
