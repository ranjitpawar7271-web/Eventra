"""Payment workflow logic, kept out of views.py per project convention.

Flow this implements (from the spec):
    Registration -> Payment -> Payment Verification -> Registration
    Confirmation -> Ticket Generation -> QR Code Generation

Ticket/QR generation is NOT called from here directly — `tickets/signals.py`
already listens for `Registration.status == 'confirmed'` and issues a
ticket automatically. Payment confirmation just flips that status, so the
existing ticket pipeline fires on its own without this app needing to
import tickets at all (keeps payments additive, same pattern tickets used
for events).
"""
from django.db import transaction
from django.utils import timezone

from events.models import Registration
from .models import Payment


def get_or_create_pending_payment(registration: Registration) -> Payment:
    """Return the registration's current payment attempt, reusing an
    existing PENDING one (e.g. user reloaded the checkout page) rather
    than minting a new transaction id every time."""
    existing = registration.payments.filter(status=Payment.STATUS_PENDING).first()
    if existing:
        return existing
    return Payment.objects.create(
        registration=registration,
        user=registration.user,
        event=registration.event,
        amount=registration.event.price,
        status=Payment.STATUS_PENDING,
    )


@transaction.atomic
def process_mock_payment(payment: Payment, method: str, simulate_failure: bool = False):
    """The mock gateway. No real card/bank data ever passes through here —
    only a method choice from the checkout form. On success, confirms the
    registration (which triggers ticket + QR generation via signal). On
    failure, the registration is left as-is so the user can retry.
    """
    from workflow.models import Notification

    if payment.status != Payment.STATUS_PENDING:
        return payment  # already resolved; don't double-process

    if simulate_failure:
        payment.mark_failed(method, "Payment declined by bank (simulated failure for demo purposes).")
        Notification.notify(
            user=payment.user,
            message=f"Payment failed for \"{payment.event.title}\". Please try again.",
            link=payment.event.get_absolute_url(),
            notification_type=Notification.TYPE_PAYMENT,
        )
        return payment

    payment.mark_successful(method)

    registration = payment.registration
    registration.status = 'confirmed'
    registration.save(update_fields=['status'])  # fires tickets.signals -> Ticket + QR

    Notification.notify(
        user=payment.user,
        message=f"Payment of ₹{payment.amount} successful for \"{payment.event.title}\". Your ticket is ready.",
        link=payment.event.get_absolute_url(),
        notification_type=Notification.TYPE_PAYMENT,
    )
    return payment


@transaction.atomic
def refund_payment(payment: Payment, amount=None):
    """Refund a successful payment and cancel the registration/ticket
    that came from it. Only callable on a successful payment."""
    from workflow.models import Notification

    if payment.status != Payment.STATUS_SUCCESSFUL:
        return False

    payment.mark_refunded(amount)

    registration = payment.registration
    registration.status = 'cancelled'
    registration.save(update_fields=['status'])  # fires tickets.signals -> Ticket cancelled

    from events import waitlist_services
    waitlist_services.promote_next_waitlisted(payment.event)

    Notification.notify(
        user=payment.user,
        message=f"₹{payment.refund_amount} refunded for \"{payment.event.title}\".",
        link=payment.event.get_absolute_url(),
        notification_type=Notification.TYPE_PAYMENT,
    )
    return True
