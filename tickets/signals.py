"""
Automatic ticket issuance, wired onto events.Registration via a signal
rather than editing events/views.py directly. This keeps Module 7 additive
only — the events app doesn't need to know tickets exist at all.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from events.models import Registration
from .models import Ticket


@receiver(post_save, sender=Registration)
def sync_ticket_with_registration(sender, instance, created, **kwargs):
    registration = instance

    # Deliberately query fresh rather than `getattr(registration, 'ticket', None)`.
    # The reverse-OneToOne descriptor caches its result on `registration`'s
    # `_state.fields_cache` the first time it's accessed. If any caller upstream
    # already touched `registration.ticket` on this exact instance before a
    # Ticket existed (e.g. a stale check earlier in the same request), that
    # negative result stays cached even after we create/update a Ticket below,
    # and a later `registration.ticket` access on that same instance would
    # incorrectly miss it. A direct queryset lookup never touches that cache.
    ticket = Ticket.objects.filter(registration=registration).first()

    if registration.status == 'confirmed':
        if ticket is None:
            ticket = Ticket.objects.create(
                registration=registration,
                ticket_type=Ticket.TYPE_FREE if registration.event.is_free else Ticket.TYPE_PAID,
            )
            _notify_registration_and_ticket(registration, ticket)
        elif ticket.status == Ticket.STATUS_CANCELLED:
            # Participant re-registered after cancelling — bring the same
            # ticket back to life rather than minting a new code, so a
            # previously-printed/emailed ticket for this registration
            # can't come back from the dead with a different code.
            ticket.status = Ticket.STATUS_ISSUED
            ticket.save(update_fields=['status'])
            _notify_registration_and_ticket(registration, ticket)
        return

    # registration.status == 'cancelled'
    if ticket is not None and ticket.status == Ticket.STATUS_ISSUED:
        # Only auto-cancel a ticket that hasn't been used yet. A ticket
        # that's already been scanned in stays as historical/audit record
        # even if the registration is later cancelled.
        ticket.status = Ticket.STATUS_CANCELLED
        ticket.save(update_fields=['status'])


def _notify_registration_and_ticket(registration, ticket):
    """Two of the spec's notification types fire off one event
    (a registration becoming confirmed always means a ticket+QR exist),
    so both are sent here rather than duplicating this signal elsewhere."""
    from workflow.models import Notification

    event = registration.event
    Notification.notify(
        registration.user,
        f"Your registration for \"{event.title}\" is confirmed.",
        link=event.get_absolute_url(),
        notification_type=Notification.TYPE_REGISTRATION,
        related_event=event,
        dedupe_key=f'registration-confirmed-{registration.pk}',
    )
    Notification.notify(
        registration.user,
        f"Your ticket for \"{event.title}\" is ready — QR code available now.",
        link=ticket.get_absolute_url(),
        notification_type=Notification.TYPE_TICKET,
        related_event=event,
        dedupe_key=f'ticket-ready-{ticket.pk}',
    )
