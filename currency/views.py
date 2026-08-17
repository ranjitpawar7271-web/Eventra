from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CurrencyForm
from .models import Currency
from .utils import SESSION_KEY


def _can_manage_currencies(user):
    """Exchange rates are platform-wide configuration, same class of
    permission as FAQ/Announcements in the `support` app — Staff/Super
    Admin, not the usual per-event organizer check."""
    return user.is_authenticated and (user.is_super_admin or user.is_staff_role)


@login_required
def currency_list(request):
    if not _can_manage_currencies(request.user):
        messages.error(request, "You don't have permission to manage currencies.")
        return redirect('dashboard:dashboard')
    return render(request, 'currency/currency_list.html', {'currencies': Currency.objects.all()})


@login_required
def currency_create(request):
    if not _can_manage_currencies(request.user):
        messages.error(request, "You don't have permission to manage currencies.")
        return redirect('dashboard:dashboard')
    if request.method == 'POST':
        form = CurrencyForm(request.POST)
        if form.is_valid():
            currency = form.save(commit=False)
            if currency.is_base:
                Currency.objects.exclude(pk=currency.pk).update(is_base=False)
            currency.save()
            messages.success(request, f"Currency '{currency.code}' added.")
            return redirect('currency:currency_list')
    else:
        form = CurrencyForm()
    return render(request, 'currency/currency_form.html', {'form': form, 'is_edit': False})


@login_required
def currency_edit(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    if not _can_manage_currencies(request.user):
        messages.error(request, "You don't have permission to manage currencies.")
        return redirect('dashboard:dashboard')
    if request.method == 'POST':
        form = CurrencyForm(request.POST, instance=currency)
        if form.is_valid():
            currency = form.save(commit=False)
            if currency.is_base:
                Currency.objects.exclude(pk=currency.pk).update(is_base=False)
            currency.save()
            messages.success(request, f"Currency '{currency.code}' updated.")
            return redirect('currency:currency_list')
    else:
        form = CurrencyForm(instance=currency)
    return render(request, 'currency/currency_form.html', {'form': form, 'is_edit': True, 'currency': currency})


@login_required
def currency_delete(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    if not _can_manage_currencies(request.user):
        messages.error(request, "You don't have permission to manage currencies.")
        return redirect('dashboard:dashboard')
    if request.method == 'POST':
        currency.delete()
        messages.success(request, "Currency removed.")
        return redirect('currency:currency_list')
    return render(request, 'currency/currency_confirm_delete.html', {'currency': currency})


@require_POST
def set_display_currency(request):
    """Public — anyone browsing, logged in or not, can switch how prices
    are displayed. This only ever changes session state, never anything
    financial in the database."""
    code = request.POST.get('currency', '').upper()
    if Currency.objects.filter(code=code).exists():
        request.session[SESSION_KEY] = code
    next_url = request.POST.get('next') or '/'
    return redirect(next_url)
