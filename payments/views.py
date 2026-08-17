from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from events.models import Event
from users.models import User
from . import services
from .models import Payment


def _can_manage_payments(user, event):
    """Same ownership rule used across the project (tickets, budget,
    event_update): staff/super admin for any event, organizer for their own."""
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


@login_required
def checkout(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.user_id != request.user.id:
        messages.error(request, "You don't have permission to view this payment.")
        return redirect('events:event_list')

    if payment.status == Payment.STATUS_SUCCESSFUL:
        messages.info(request, "This payment was already completed.")
        return redirect('events:event_detail', slug=payment.event.slug)

    return render(request, 'payments/checkout.html', {
        'payment': payment,
        'event': payment.event,
        'methods': Payment.METHOD_CHOICES,
    })


@login_required
@require_POST
def process_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.user_id != request.user.id:
        messages.error(request, "You don't have permission to act on this payment.")
        return redirect('events:event_list')

    method = request.POST.get('payment_method', Payment.METHOD_CARD)
    simulate_failure = request.POST.get('action') == 'simulate_failure'

    if method not in dict(Payment.METHOD_CHOICES):
        messages.error(request, "Please choose a valid payment method.")
        return redirect('payments:checkout', payment_id=payment.id)

    payment = services.process_mock_payment(payment, method, simulate_failure=simulate_failure)

    if payment.is_successful:
        messages.success(request, f"Payment successful! Your ticket for \"{payment.event.title}\" is ready.")
        return redirect('events:event_detail', slug=payment.event.slug)

    messages.error(request, f"Payment failed: {payment.failure_reason}")
    return redirect('payments:checkout', payment_id=payment.id)


@login_required
def my_payments(request):
    payments = Payment.objects.filter(user=request.user).select_related('event').order_by('-created_at')
    return render(request, 'payments/my_payments.html', {'payments': payments})


@login_required
def event_payments(request, slug):
    """Organizer/staff view of all payments for one event, with refund action."""
    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_payments(request.user, event):
        messages.error(request, "You don't have permission to view this event's payments.")
        return redirect('events:event_detail', slug=slug)

    payments = Payment.objects.filter(event=event).select_related('user').order_by('-created_at')
    total_revenue = sum((p.amount for p in payments if p.status == Payment.STATUS_SUCCESSFUL), start=0)
    return render(request, 'payments/event_payments.html', {
        'event': event,
        'payments': payments,
        'total_revenue': total_revenue,
    })


@login_required
@require_POST
def refund(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if not _can_manage_payments(request.user, payment.event):
        messages.error(request, "You don't have permission to refund this payment.")
        return redirect('events:event_detail', slug=payment.event.slug)

    if services.refund_payment(payment):
        messages.success(request, f"Refunded ₹{payment.refund_amount} to {payment.user}.")
    else:
        messages.error(request, "Only a successful payment can be refunded.")
    return redirect('payments:event_payments', slug=payment.event.slug)
