"""Turns a user's message into real Eventra data, never into a guess.

Architecture (matches the spec):
    message -> classify_intent() -> is it organizer-only? enforce here,
    not by trusting the LLM -> fetch real rows for that intent -> a plain
    text "FACTS" block -> handed to the LLM in services.py, which is told
    to answer using ONLY those facts.

Intent classification is deliberately simple keyword matching, not a
second LLM call — it's fast, free, fully deterministic, and the
permission check downstream depends on classifying correctly, so
keeping it auditable/testable as plain Python is safer than trusting an
LLM to both classify AND self-police what it's allowed to say.
"""
import re
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from events.models import Event, Registration
from tickets.models import Ticket
from users.models import User

# Intents that expose operational data no participant should see —
# enforced before any DB query runs for these, not left to prompt
# instructions the model could be talked out of.
ORGANIZER_ONLY_INTENTS = {
    'revenue', 'attendance_today', 'top_event', 'tickets_sold', 'participants_count',
}

_STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'for', 'of', 'in', 'on', 'at', 'to', 'how', 'many',
    'what', 'when', 'where', 'my', 'i', 'can', 'do', 'does', 'event', 'events', 'me',
    'show', 'find', 'and', 'about', 'this', 'that', 'left', 'available',
}


def is_manager(user):
    return user.is_super_admin or user.is_staff_role or user.role == User.ORGANIZER


def classify_intent(message: str) -> str:
    m = message.lower()

    def has(*words):
        return any(w in m for w in words)

    if has('revenue', 'earning', 'earnings', 'income', 'profit'):
        return 'revenue'
    if has('checked in today', "today's attendance", 'attendance today', 'how many checked in'):
        return 'attendance_today'
    if has('highest registration', 'most popular', 'top event', 'best selling'):
        return 'top_event'
    if has('tickets sold', 'ticket sold', 'how many tickets'):
        return 'tickets_sold'
    if has('how many participants', 'how many registered', 'total registrations', 'registration count'):
        return 'participants_count'
    if has('my ticket', 'my tickets', 'download my ticket'):
        return 'my_tickets'
    if has('certificate'):
        return 'certificate'
    if has('my registration', 'my registrations', 'registered events', 'my events', 'registration status'):
        return 'my_registrations'
    if has('this week', 'upcoming events', "what's on", 'available events', 'show events', 'what events'):
        return 'upcoming_events'
    if has('full', 'sold out', 'any seats', 'seats left', 'seats remaining', 'how many seats'):
        return 'seats_and_availability'
    if has('price', 'cost', 'how much', 'fee'):
        return 'event_price'
    if has('where', 'location', 'venue', 'address'):
        return 'event_location'
    if has('when', 'what time', 'start time', 'date'):
        return 'event_time'
    if has('status'):
        return 'event_status'
    if has('register', 'how do i sign up', 'how to join'):
        return 'how_to_register'
    return 'general'


def _match_event(message: str, queryset):
    """Best-effort match of a mentioned event name against a queryset,
    by word overlap with the title. Returns None if nothing overlaps —
    callers must treat that as "no specific event was named", not guess."""
    words = set(re.findall(r'[a-z0-9]+', message.lower())) - _STOPWORDS
    if not words:
        return None
    best, best_score = None, 0
    for event in queryset:
        title_words = set(re.findall(r'[a-z0-9]+', event.title.lower()))
        score = len(words & title_words)
        if score > best_score:
            best, best_score = event, score
    return best


def _event_fact(event):
    seats_left = max(event.capacity - event.seats_taken, 0)
    lines = [
        f"- Title: {event.title}",
        f"  Date/Time: {event.start_date.strftime('%b %d, %Y at %I:%M %p')}",
        f"  Location: {event.location}",
        f"  Price: {'Free' if event.is_free else f'₹{event.price}'}",
        f"  Capacity: {event.capacity}, Seats left: {seats_left}",
        f"  Full: {'Yes' if event.is_full else 'No'}",
        f"  Status: {event.get_status_display()}",
    ]
    if event.average_rating:
        lines.append(f"  Rating: {event.average_rating}/5 ({event.review_count} reviews)")
    return "\n".join(lines)


def build_facts(user, message: str, intent: str) -> str:
    """The single source of truth handed to the LLM. Every branch here
    queries the real database — nothing here is ever a guess the model
    could instead have made up itself."""

    if intent == 'upcoming_events':
        events = Event.objects.filter(status='published', start_date__gte=timezone.now()).order_by('start_date')[:6]
        if not events:
            return "There are no upcoming published events right now."
        return "Upcoming events:\n" + "\n\n".join(_event_fact(e) for e in events)

    if intent in ('event_price', 'event_location', 'event_time', 'event_status', 'seats_and_availability', 'how_to_register'):
        event = _match_event(message, Event.objects.filter(status='published'))
        if event:
            return _event_fact(event)
        events = Event.objects.filter(status='published', start_date__gte=timezone.now()).order_by('start_date')[:5]
        return (
            "No specific event was recognized in the question. Here are the upcoming events "
            "the user could be asking about:\n" + "\n\n".join(_event_fact(e) for e in events)
        )

    if intent == 'my_registrations':
        regs = Registration.objects.filter(user=user, status='confirmed').select_related('event').order_by('event__start_date')[:10]
        if not regs:
            return "This user has no confirmed registrations."
        lines = [f"- {r.event.title} on {r.event.start_date.strftime('%b %d, %Y')} — status: confirmed" for r in regs]
        pending = Registration.objects.filter(user=user, status='pending_payment').select_related('event')[:5]
        for p in pending:
            lines.append(f"- {p.event.title} — registration pending payment")
        return "This user's registrations:\n" + "\n".join(lines)

    if intent == 'my_tickets':
        tickets = Ticket.objects.filter(registration__user=user).select_related('registration__event').order_by('-issued_at')[:10]
        if not tickets:
            return "This user has no tickets yet."
        lines = [
            f"- {t.event.title}: ticket {t.ticket_code}, status {t.get_status_display()}, view at /tickets/{t.ticket_code}/"
            for t in tickets
        ]
        return "This user's tickets:\n" + "\n".join(lines)

    if intent == 'certificate':
        from certificates.models import Certificate
        certs = Certificate.objects.filter(ticket__registration__user=user, revoked=False).select_related('ticket__registration__event')[:10]
        if not certs:
            return (
                "This user has no certificates yet. Certificates are issued after a participant "
                "attends (checks in to) an event whose organizer has enabled certificates."
            )
        lines = [
            f"- {c.event.title}: {c.get_cert_type_display()}, download at /certificates/{c.certificate_code}/pdf/"
            for c in certs
        ]
        return "This user's certificates:\n" + "\n".join(lines)

    # --- Organizer-only intents below (permission already checked by caller) ---

    manageable = Event.objects.all() if (user.is_super_admin or user.is_staff_role) else Event.objects.filter(organizer=user)

    if intent == 'participants_count':
        event = _match_event(message, manageable)
        if event:
            count = Registration.objects.filter(event=event, status='confirmed').count()
            return f"{event.title}: {count} confirmed participant(s) out of {event.capacity} capacity."
        rows = manageable.annotate(reg_count=Count('registrations', filter=Q(registrations__status='confirmed'), distinct=True)).order_by('-start_date')[:8]
        if not rows:
            return "This organizer has no events."
        return "Registration counts by event:\n" + "\n".join(f"- {e.title}: {e.reg_count} confirmed" for e in rows)

    if intent == 'tickets_sold':
        event = _match_event(message, manageable)
        qs = Ticket.objects.filter(registration__event=event) if event else Ticket.objects.filter(registration__event__in=manageable)
        sold = qs.exclude(status__in=[Ticket.STATUS_CANCELLED, Ticket.STATUS_REFUNDED]).count()
        label = event.title if event else "all of this organizer's events"
        return f"Tickets sold for {label}: {sold}."

    if intent == 'attendance_today':
        today = timezone.localdate()
        event = _match_event(message, manageable)
        qs = Ticket.objects.filter(registration__event=event) if event else Ticket.objects.filter(registration__event__in=manageable)
        checked_in_today = qs.filter(status=Ticket.STATUS_CHECKED_IN, checked_in_at__date=today).count()
        total_registered = qs.exclude(status__in=[Ticket.STATUS_CANCELLED, Ticket.STATUS_REFUNDED]).count()
        label = event.title if event else "all of this organizer's events"
        return f"Today's attendance for {label}: {checked_in_today} checked in out of {total_registered} registered."

    if intent == 'revenue':
        from payments.models import Payment
        event = _match_event(message, manageable)
        qs = Payment.objects.filter(status='successful', event=event) if event else Payment.objects.filter(status='successful', event__in=manageable)
        total = qs.aggregate(total=Sum('amount'))['total'] or 0
        label = event.title if event else "all of this organizer's events"
        return f"Revenue for {label}: ₹{total} from {qs.count()} successful payment(s)."

    if intent == 'top_event':
        rows = manageable.annotate(reg_count=Count('registrations', filter=Q(registrations__status='confirmed'), distinct=True)).order_by('-reg_count')[:3]
        if not rows:
            return "This organizer has no events."
        return "Top events by registration count:\n" + "\n".join(f"- {e.title}: {e.reg_count} confirmed registrations" for e in rows)

    # 'general' or unrecognized — hand back a small helpful snapshot
    events = Event.objects.filter(status='published', start_date__gte=timezone.now()).order_by('start_date')[:3]
    return (
        "No specific question type was recognized. A few upcoming events, in case they're helpful:\n"
        + "\n\n".join(_event_fact(e) for e in events)
    )
