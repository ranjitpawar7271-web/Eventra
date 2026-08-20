"""Waitlist workflow logic for events at capacity.

Kept out of views.py (Task/notes convention in this project: "Use
Services/utilities where appropriate") since promotion touches three
models (WaitlistEntry, Registration, Notification) inside a transaction
and doesn't belong inline in a request handler.
"""
from django.db import transaction
from django.utils import timezone

from .models import Event, Registration, WaitlistEntry


def _next_position(event):
    last = (
        WaitlistEntry.objects.filter(event=event, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED])
        .order_by('-position')
        .first()
    )
    return (last.position + 1) if last else 1


@transaction.atomic
def join_waitlist(event: Event, user):
    """Add `user` to `event`'s waitlist. Returns (entry, created).

    Refuses if:
    - the event isn't genuinely open for registration (draft, cancelled,
      completed, or already started) — mirrors events.views.join_waitlist's
      guard here too, so a direct call from anywhere else in the codebase
      can't bypass it (defense in depth, not just a view-level check);
    - the user already has an active entry (no duplicates); or
    - the user already has an active registration (they don't need a
      waitlist spot).
    """
    if not event.is_registration_open:
        return None, False

    if Registration.objects.filter(event=event, user=user, status='confirmed').exists():
        return None, False

    existing = WaitlistEntry.objects.filter(
        event=event, user=user, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
    ).first()
    if existing:
        return existing, False

    entry = WaitlistEntry.objects.create(
        event=event, user=user, position=_next_position(event), status=WaitlistEntry.STATUS_WAITING
    )
    return entry, True


@transaction.atomic
def leave_waitlist(event: Event, user):
    entry = WaitlistEntry.objects.filter(
        event=event, user=user, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
    ).first()
    if not entry:
        return False
    entry.status = WaitlistEntry.STATUS_CANCELLED
    entry.save(update_fields=['status'])
    _resequence(event)
    return True


def _resequence(event):
    """Collapse gaps left by cancelled/expired entries so positions stay 1, 2, 3..."""
    active = list(
        WaitlistEntry.objects.filter(
            event=event, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
        ).order_by('position', 'joined_at')
    )
    for idx, entry in enumerate(active, start=1):
        if entry.position != idx:
            entry.position = idx
            entry.save(update_fields=['position'])


@transaction.atomic
def promote_next_waitlisted(event: Event):
    """Called whenever a seat opens up (cancellation, capacity increase).

    Moves the front-of-queue entry to STATUS_NOTIFIED (not straight to a
    confirmed Registration) and starts an invitation-expiry window, per
    the spec's "Notify participant -> Allow registration -> Confirm
    registration" workflow — promotion offers the seat, it doesn't force
    it on someone who may no longer want it.
    """
    from workflow.models import Notification

    if event.is_full:
        return None

    if not event.is_registration_open:
        # Event was cancelled/completed (or somehow reverted to draft)
        # since the seat opened up — don't keep notifying people about a
        # seat they can no longer actually take.
        return None

    entry = (
        WaitlistEntry.objects.filter(event=event, status=WaitlistEntry.STATUS_WAITING)
        .order_by('position', 'joined_at')
        .first()
    )
    if not entry:
        return None

    entry.status = WaitlistEntry.STATUS_NOTIFIED
    entry.notified_at = timezone.now()
    entry.invitation_expires_at = timezone.now() + timezone.timedelta(hours=WaitlistEntry.INVITE_WINDOW_HOURS)
    entry.save(update_fields=['status', 'notified_at', 'invitation_expires_at'])

    Notification.notify(
        user=entry.user,
        message=f"A seat opened up for \"{event.title}\"! Register within 48 hours to claim it.",
        link=event.get_absolute_url(),
        notification_type=Notification.TYPE_REMINDER,
    )
    return entry


@transaction.atomic
def claim_waitlist_seat(event: Event, user):
    """A notified user completing registration from their waitlist invite.

    For free events this confirms the registration outright. For paid
    events it hands back a `pending_payment` Registration instead —
    the caller (events.views.event_register) is responsible for routing
    that into the normal payment checkout, same as any other paid
    registration; a waitlist invite doesn't skip payment.

    Returns None if there was no valid (non-expired) invitation and the
    normal event_register flow should handle it instead.
    """
    entry = WaitlistEntry.objects.select_for_update().filter(
        event=event, user=user, status=WaitlistEntry.STATUS_NOTIFIED
    ).first()
    if not entry or entry.invitation_is_expired:
        if entry and entry.invitation_is_expired:
            entry.status = WaitlistEntry.STATUS_EXPIRED
            entry.save(update_fields=['status'])
            _resequence(event)
            promote_next_waitlisted(event)
        return None

    if not event.is_registration_open:
        # The invite is still live, but the event itself was
        # cancelled/completed in the meantime — the seat can't be
        # claimed. events.views.event_register also checks this before
        # ever calling in here; this is the defense-in-depth copy for
        # any other caller.
        return None

    if event.is_full:
        return None

    if event.is_free:
        registration, _ = Registration.objects.get_or_create(
            event=event, user=user, defaults={'status': 'confirmed'}
        )
        registration.status = 'confirmed'
        registration.save(update_fields=['status'])
    else:
        registration, created = Registration.objects.get_or_create(
            event=event, user=user, defaults={'status': 'pending_payment'}
        )
        if not created and registration.status == 'cancelled':
            registration.status = 'pending_payment'
            registration.save(update_fields=['status'])

    entry.status = WaitlistEntry.STATUS_PROMOTED
    entry.save(update_fields=['status'])
    _resequence(event)
    return registration


def expire_stale_invitations(event: Event = None):
    """Sweep NOTIFIED entries whose invite window passed, promoting the
    next person in line for each. Safe to call from a scheduled command
    or opportunistically from a view — idempotent either way."""
    qs = WaitlistEntry.objects.filter(status=WaitlistEntry.STATUS_NOTIFIED)
    if event:
        qs = qs.filter(event=event)
    for entry in qs.filter(invitation_expires_at__lt=timezone.now()):
        entry.status = WaitlistEntry.STATUS_EXPIRED
        entry.save(update_fields=['status'])
        _resequence(entry.event)
        promote_next_waitlisted(entry.event)