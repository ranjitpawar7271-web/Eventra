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

    Capacity is re-checked here, under a row lock, right before a
    registration is confirmed. Without this, two pending registrations for
    the same event's last seat can both end up 'confirmed' if their
    payments are completed close together — `seats_taken` only counts
    'confirmed' registrations (a 'pending_payment' registration does not
    reserve a seat), so nothing else in the system prevents this on its
    own. See TASK 2/3 in the accompanying notes for the full trace.
    """
    from workflow.models import Notification
    from events.models import Event, Registration
    from events import waitlist_services

    # Lock the Payment row first. Two near-simultaneous submits for the
    # exact same payment (double form submit, retried request) must not
    # both get past the "already resolved" guard below — the second one
    # blocks here until the first's transaction commits, then sees the
    # updated status and bails out instead of re-processing.
    payment = Payment.objects.select_for_update().get(pk=payment.pk)

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

    # Lock the Event row for the rest of this transaction. This is the
    # single serialization point for capacity: whichever confirmation gets
    # here first for a given event holds the lock until it commits, so a
    # second concurrent confirmation for that same event can't read a
    # stale seat count and also win the last seat (the bug this fixes).
    # Only this one row is locked — not the whole events/registrations
    # table — so unrelated events confirm concurrently without contention.
    event = Event.objects.select_for_update().get(pk=payment.event_id)
    registration = Registration.objects.select_for_update().get(pk=payment.registration_id)

    if registration.status == 'confirmed':
        # Already confirmed (e.g. this exact payment was processed by a
        # racing request that got here microseconds earlier). Stay
        # idempotent: acknowledge success without re-confirming or
        # re-notifying instead of erroring.
        payment.mark_successful(method)
        return payment

    if registration.status == 'cancelled' or event.status in ('cancelled', 'completed') or event.has_ended:
        # Registration or event lifecycle moved on while this payment was
        # pending (organizer cancelled the event, the event finished, or
        # the registration itself was cancelled/refunded elsewhere).
        payment.mark_failed(
            method,
            "This registration is no longer valid for payment — the event or "
            "registration changed before payment could be confirmed.",
        )
        Notification.notify(
            user=payment.user,
            message=f"Payment for \"{event.title}\" could not be completed because the "
                     "registration is no longer valid. You have not been charged.",
            link=event.get_absolute_url(),
            notification_type=Notification.TYPE_PAYMENT,
        )
        return payment

    seats_taken = Registration.objects.filter(event=event, status='confirmed').count()
    if seats_taken >= event.capacity:
        # The exact race in the bug report: this registration's seat was
        # taken by someone else's confirmation while this payment was
        # still pending. This is a mock gateway, so "not charging" is
        # simply never marking the payment successful — fail it, free the
        # registration, and route the user through the project's existing
        # waitlist mechanism instead of silently over-booking the event.
        payment.mark_failed(
            method,
            "This event reached capacity while your payment was pending. "
            "You have not been charged.",
        )
        registration.status = 'cancelled'
        registration.save(update_fields=['status'])  # fires tickets.signals (no-op: no ticket existed)
        waitlist_services.join_waitlist(event, payment.user)
        Notification.notify(
            user=payment.user,
            message=f"\"{event.title}\" filled up before your payment could be confirmed. "
                     "You have not been charged, and you've been added to the waitlist.",
            link=event.get_absolute_url(),
            notification_type=Notification.TYPE_CAPACITY,
        )
        return payment

    payment.mark_successful(method)
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