"""Views for static marketing pages and custom error handlers."""
from django.shortcuts import render
from django.contrib import messages
from django.utils import timezone

from events.models import Event
from categories.models import Category


def home(request):
    upcoming_events = (
        Event.objects.filter(status='published', start_date__gte=timezone.now())
        .select_related('category', 'organizer')
        .order_by('start_date')[:6]
    )
    categories = Category.objects.all()[:8]
    context = {
        'upcoming_events': upcoming_events,
        'categories': categories,
        'total_events': Event.objects.filter(status='published').count(),
        'total_categories': Category.objects.count(),
    }
    return render(request, 'home.html', context)


def about(request):
    return render(request, 'pages/about.html')


def contact(request):
    if request.method == 'POST':
        messages.success(request, "Thanks for reaching out! Our team will get back to you shortly.")
        from django.shortcuts import redirect
        return redirect('pages:contact')
    return render(request, 'pages/contact.html')


def faq(request):
    return render(request, 'pages/faq.html')


def privacy_policy(request):
    return render(request, 'pages/privacy_policy.html')


def terms_conditions(request):
    return render(request, 'pages/terms_conditions.html')


def error_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def error_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)


def error_500(request):
    return render(request, 'errors/500.html', status=500)
