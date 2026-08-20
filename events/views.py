from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
import datetime

from categories.models import Category
from users.models import User
from venues.models import VenueBooking
from wishlist.models import FavoriteEvent
from .forms import EventForm
from .event_templates import EVENT_TEMPLATES, get_template_initial
from .ics_utils import build_google_calendar_url, build_ics_bytes
from .models import Event, Registration, WaitlistEntry
from . import waitlist_services
from reviews.models import Review
from reviews.views import can_review
# Reuses the project's one existing QR-rendering helper (tickets/utils.py)
# instead of adding a second `qrcode` call site. That function is a plain
# "string -> PNG bytes" helper with no Ticket-model coupling, so importing
# it here doesn't pull in any ticket/check-in behavior.
from tickets.utils import render_qr_png


def event_list(request):
    events = Event.objects.filter(status='published').select_related('category', 'organizer')

    query = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category', '')
    location = request.GET.get('location', '').strip()
    organizer_id = request.GET.get('organizer', '')
    date_range = request.GET.get('date_range', '')
    price_type = request.GET.get('price_type', '')
    price_min = request.GET.get('price_min', '').strip()
    price_max = request.GET.get('price_max', '').strip()
    availability = request.GET.get('availability', '')
    min_rating = request.GET.get('min_rating', '').strip()
    sort = request.GET.get('sort', '')

    if query:
        events = events.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
            | Q(location__icontains=query)
            | Q(organizer__first_name__icontains=query)
            | Q(organizer__last_name__icontains=query)
            | Q(organizer__username__icontains=query)
        )
    if category_slug:
        events = events.filter(category__slug=category_slug)
    if location:
        events = events.filter(location__icontains=location)
    if organizer_id:
        events = events.filter(organizer_id=organizer_id)

    now = timezone.now()
    if date_range == 'today':
        events = events.filter(start_date__date=now.date())
    elif date_range == 'this_week':
        events = events.filter(start_date__date__range=[now.date(), now.date() + datetime.timedelta(days=7)])
    elif date_range == 'this_month':
        events = events.filter(start_date__year=now.year, start_date__month=now.month)
    elif date_range == 'upcoming':
        events = events.filter(start_date__gte=now)

    if price_type == 'free':
        events = events.filter(price=0)
    elif price_type == 'paid':
        events = events.filter(price__gt=0)
    if price_min:
        try:
            events = events.filter(price__gte=float(price_min))
        except ValueError:
            pass
    if price_max:
        try:
            events = events.filter(price__lte=float(price_max))
        except ValueError:
            pass

    # Annotate once, reused by both the availability filter and the
    # "Most Popular" / "Highest Rated" sort options below — a single
    # annotated queryset instead of separate counts per branch.
    events = events.annotate(
        confirmed_count=Count('registrations', filter=Q(registrations__status='confirmed'), distinct=True),
        avg_rating=Avg('reviews__rating'),
    )

    if availability == 'available':
        events = events.filter(confirmed_count__lt=F('capacity'))
    elif availability == 'full':
        events = events.filter(confirmed_count__gte=F('capacity'))

    if min_rating:
        try:
            events = events.filter(avg_rating__gte=float(min_rating))
        except ValueError:
            pass

    sort_options = {
        'upcoming': 'start_date',
        'newest': '-created_at',
        'popular': '-confirmed_count',
        'rating': '-avg_rating',
        'price_low': 'price',
        'price_high': '-price',
    }
    events = events.order_by(sort_options.get(sort, 'start_date'))

    paginator = Paginator(events, 9)
    page_obj = paginator.get_page(request.GET.get('page'))

    favorited_event_ids = set()
    if request.user.is_authenticated:
        favorited_event_ids = set(
            FavoriteEvent.objects.filter(
                user=request.user, event__in=page_obj.object_list
            ).values_list('event_id', flat=True)
        )

    context = {
        'page_obj': page_obj,
        'categories': Category.objects.all(),
        'organizers': User.objects.filter(organized_events__status='published').distinct().order_by('username'),
        'query': query,
        'selected_category': category_slug,
        'selected_location': location,
        'selected_organizer': organizer_id,
        'selected_date_range': date_range,
        'selected_price_type': price_type,
        'selected_price_min': price_min,
        'selected_price_max': price_max,
        'selected_availability': availability,
        'selected_min_rating': min_rating,
        'selected_sort': sort,
        'favorited_event_ids': favorited_event_ids,
    }
    return render(request, 'events/event_list.html', context)


def event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.select_related('category', 'organizer'), slug=slug
    )
    is_registered = False
    pending_payment = None
    if request.user.is_authenticated:
        is_registered = Registration.objects.filter(
            event=event, user=request.user, status='confirmed'
        ).exists()
        if not is_registered:
            pending_reg = Registration.objects.filter(
                event=event, user=request.user, status='pending_payment'
            ).first()
            if pending_reg:
                pending_payment = pending_reg.payments.filter(status='pending').first()

    # Read-only budget summary for whoever can manage this event's
    # finances (Module 6). Kept as a plain query rather than importing
    # budget's permission helper here, to avoid a circular import between
    # events and budget — the check itself is simple enough to inline.
    budget = None
    can_view_budget = request.user.is_authenticated and request.user.can_manage_events and (
        request.user.is_super_admin or request.user.is_staff_role or event.organizer_id == request.user.id
    )
    if can_view_budget:
        budget = getattr(event, 'budget', None)

    # Sponsorships (Module 10) — same visibility rule as the budget panel,
    # since a sponsorship deal is financial/budget-adjacent data.
    sponsorships = event.sponsorships.select_related('sponsor').all() if can_view_budget else []

    is_favorited = False
    waitlist_entry = None
    can_review_event = False
    my_review = None
    if request.user.is_authenticated:
        is_favorited = FavoriteEvent.objects.filter(user=request.user, event=event).exists()
        waitlist_entry = WaitlistEntry.objects.filter(
            event=event, user=request.user, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
        ).first()
        my_review = Review.objects.filter(event=event, user=request.user).first()
        can_review_event = can_review(request.user, event)

    context = {
        'event': event,
        'is_registered': is_registered,
        'can_view_budget': can_view_budget,
        'budget': budget,
        'sponsorships': sponsorships,
        'is_favorited': is_favorited,
        'google_calendar_url': build_google_calendar_url(event),
        'waitlist_entry': waitlist_entry,
        'pending_payment': pending_payment,
        'waitlist_count': event.waitlist_entries.filter(
            status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
        ).count(),
        'can_review': can_review_event,
        'my_review': my_review,
    }
    return render(request, 'events/event_detail.html', context)


def event_registration_qr(request, slug):
    """Registration QR code — completely separate from the ticket QR in
    the `tickets` app (that one is for post-payment check-in, this one is
    for *reaching* the event's public registration page in the first
    place). It is intentionally public/unauthenticated and un-gated by
    ownership: it just renders a PNG of the event's own public detail-page
    URL, exactly like scanning it, typing it, or clicking a shared link
    all land on the same page and go through the same server-side
    registration checks (capacity, lifecycle, auth) — this view never
    touches Registration/Payment/Ticket at all, so there is only one real
    registration code path anywhere in the project.

    No image file is written to disk (matching how tickets/views.py's
    ticket_qr_image works) — the PNG is regenerated on every request from
    the event's current slug, so nothing gets out of sync if a slug were
    ever to change.
    """
    event = get_object_or_404(Event, slug=slug)
    registration_url = request.build_absolute_uri(event.get_absolute_url())
    png = render_qr_png(registration_url)
    return HttpResponse(png, content_type='image/png')


def _sync_venue_booking(event, user):
    """Keep a VenueBooking in lockstep with an Event's venue/date selection.

    - No venue selected: cancel any existing linked booking (venue freed up).
    - Venue selected: create the booking, or update the existing one's dates.
    Availability was already validated in EventForm.clean(), so this should
    not normally raise — but VenueBooking.save() re-validates via
    full_clean() as a defense-in-depth safety net.
    """
    existing = event.venue_bookings.filter(status='confirmed').first()

    if not event.venue:
        if existing:
            existing.status = 'cancelled'
            existing.save()
        return

    if existing:
        existing.venue = event.venue
        existing.start_datetime = event.start_date
        existing.end_datetime = event.end_date
        existing.purpose = f"Event: {event.title}"
        existing.save()
    else:
        VenueBooking.objects.create(
            venue=event.venue,
            event=event,
            booked_by=user,
            purpose=f"Event: {event.title}",
            start_datetime=event.start_date,
            end_datetime=event.end_date,
            status='confirmed',
        )


@login_required
def event_create(request):
    if not request.user.can_manage_events:
        messages.error(
            request,
            "Your account role doesn't allow creating events. "
            "Contact an admin if you need Organizer access."
        )
        return redirect('dashboard:dashboard')

    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            _sync_venue_booking(event, request.user)
            if not request.user.is_organizer:
                request.user.is_organizer = True
                request.user.save(update_fields=['is_organizer'])
            messages.success(request, "Event created successfully.")
            return redirect('events:event_detail', slug=event.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        initial = get_template_initial(request.GET.get('template', ''))
        form = EventForm(initial=initial, user=request.user)
    return render(request, 'events/event_form.html', {'form': form, 'title': 'Create Event'})


@login_required
def event_create_start(request):
    """Event Templates (Module 10): a picker page linking into the
    normal event_create form with `?template=<key>` pre-filling it, or a
    'start from scratch' link straight to the blank form. Purely a
    convenience layer in front of the existing create flow — no new URL
    behavior for event_create itself, so nothing that already links or
    posts there needed to change."""
    if not request.user.can_manage_events:
        messages.error(
            request,
            "Your account role doesn't allow creating events. "
            "Contact an admin if you need Organizer access."
        )
        return redirect('dashboard:dashboard')
    return render(request, 'events/event_template_picker.html', {'templates': EVENT_TEMPLATES})


@login_required
def event_update(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if event.organizer != request.user and not request.user.is_staff and not request.user.is_super_admin and not request.user.is_staff_role:
        messages.error(request, "You are not authorized to edit this event.")
        return redirect('events:event_detail', slug=slug)

    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event, user=request.user)
        if form.is_valid():
            form.save()
            _sync_venue_booking(event, request.user)
            messages.success(request, "Event updated successfully.")
            return redirect('events:event_detail', slug=event.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = EventForm(instance=event, user=request.user)
    return render(request, 'events/event_form.html', {'form': form, 'title': 'Update Event', 'event': event})


@login_required
def event_delete(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if event.organizer != request.user and not request.user.is_staff and not request.user.is_super_admin and not request.user.is_staff_role:
        messages.error(request, "You are not authorized to delete this event.")
        return redirect('events:event_detail', slug=slug)

    if request.method == 'POST':
        event.delete()
        messages.success(request, "Event deleted successfully.")
        return redirect('events:my_events')
    return render(request, 'events/event_confirm_delete.html', {'event': event})


@login_required
def event_participants(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if event.organizer != request.user and not request.user.is_staff and not request.user.is_super_admin and not request.user.is_staff_role:
        messages.error(request, "You are not authorized to view participants for this event.")
        return redirect('events:event_detail', slug=slug)

    participants = (
        Registration.objects.filter(event=event)
        .exclude(status='cancelled')
        .select_related('user', 'ticket')
        .prefetch_related('payments')
        .order_by('-registered_at')
    )

    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment', '')
    attendance_filter = request.GET.get('attendance', '')

    if query:
        participants = participants.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
        )
    if status_filter:
        participants = participants.filter(status=status_filter)
    if payment_filter == 'paid':
        participants = participants.filter(payments__status='successful').distinct()
    elif payment_filter == 'unpaid':
        participants = participants.filter(status='pending_payment').distinct()
    elif payment_filter == 'refunded':
        participants = participants.filter(payments__status='refunded').distinct()
    if attendance_filter == 'checked_in':
        participants = participants.filter(ticket__status='checked_in')
    elif attendance_filter == 'not_arrived':
        participants = participants.filter(status='confirmed').exclude(ticket__status='checked_in')

    context = {
        'event': event,
        'participants': participants,
        'query': query,
        'status_filter': status_filter,
        'payment_filter': payment_filter,
        'attendance_filter': attendance_filter,
        'is_paid_event': not event.is_free,
    }
    return render(request, 'events/event_participants.html', context)


@login_required
def event_participants_export(request, slug):
    """CSV export of the participant list, honoring the same filters as
    the on-screen table (search/status/payment/attendance) so what an
    organizer sees is what they export."""
    import csv

    event = get_object_or_404(Event, slug=slug)
    if event.organizer != request.user and not request.user.is_staff and not request.user.is_super_admin and not request.user.is_staff_role:
        messages.error(request, "You are not authorized to export participants for this event.")
        return redirect('events:event_detail', slug=slug)

    participants = Registration.objects.filter(event=event).exclude(status='cancelled').select_related('user').prefetch_related('payments')

    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment', '')
    attendance_filter = request.GET.get('attendance', '')
    if query:
        participants = participants.filter(
            Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query) | Q(user__email__icontains=query)
        )
    if status_filter:
        participants = participants.filter(status=status_filter)
    if payment_filter == 'paid':
        participants = participants.filter(payments__status='successful').distinct()
    elif payment_filter == 'unpaid':
        participants = participants.filter(status='pending_payment').distinct()
    elif payment_filter == 'refunded':
        participants = participants.filter(payments__status='refunded').distinct()
    if attendance_filter == 'checked_in':
        participants = participants.filter(ticket__status='checked_in')
    elif attendance_filter == 'not_arrived':
        participants = participants.filter(status='confirmed').exclude(ticket__status='checked_in')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{event.slug}-participants.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Phone', 'Registration Status', 'Registered On', 'Payment Status', 'Ticket Code', 'Check-in Status', 'Check-in Time'])
    for reg in participants:
        payment = reg.payments.order_by('-created_at').first()
        ticket = getattr(reg, 'ticket', None)
        writer.writerow([
            reg.user.get_full_name() or reg.user.username,
            reg.user.email,
            reg.user.phone_number or '',
            reg.get_status_display(),
            reg.registered_at.strftime('%Y-%m-%d %H:%M'),
            payment.get_status_display() if payment else ('Free' if event.is_free else '—'),
            ticket.ticket_code if ticket else '—',
            ticket.get_status_display() if ticket else '—',
            ticket.checked_in_at.strftime('%Y-%m-%d %H:%M') if ticket and ticket.checked_in_at else '—',
        ])
    return response


@login_required
def my_events(request):
    events = Event.objects.filter(organizer=request.user).select_related('category')
    return render(request, 'events/my_events.html', {'events': events})


@login_required
@require_POST
def event_register(request, slug):
    event = get_object_or_404(Event, slug=slug)

    from payments import services as payment_services

    existing = Registration.objects.filter(event=event, user=request.user).first()
    if existing and existing.status == 'confirmed':
        messages.info(request, "You're already registered for this event.")
        return redirect('events:event_detail', slug=slug)

    # Server-side lifecycle check — the register button/form is already
    # hidden in the template for closed events, but that's UI only. A
    # direct POST (crafted request, stale tab, replayed form) must be
    # rejected here too: no registering for a draft, cancelled, or
    # completed event, and none after the event has already started.
    if not event.is_registration_open:
        messages.error(
            request,
            f"Registration for \"{event.title}\" is closed — it's either "
            "not published yet, cancelled, completed, or already underway."
        )
        return redirect('events:event_detail', slug=slug)

    # A notified waitlist entry gets first claim on the seat it was
    # offered, even if someone else's request raced in first.
    claimed = waitlist_services.claim_waitlist_seat(event, request.user)
    if claimed:
        if claimed.status == 'confirmed':
            messages.success(request, f"You're registered for {event.title}!")
            return redirect('events:event_detail', slug=slug)
        payment = payment_services.get_or_create_pending_payment(claimed)
        return redirect('payments:checkout', payment_id=payment.id)

    if event.is_full and not (existing and existing.status == 'pending_payment'):
        messages.warning(request, "Sorry, this event is already full. You can join the waitlist instead.")
        return redirect('events:event_detail', slug=slug)

    if event.is_free:
        registration, created = Registration.objects.get_or_create(
            event=event, user=request.user, defaults={'status': 'confirmed'}
        )
        if not created:
            registration.status = 'confirmed'
            registration.save(update_fields=['status'])
        messages.success(request, f"You're registered for {event.title}!")
        return redirect('events:event_detail', slug=slug)

    # Paid event: create/reuse a pending registration and send the user
    # to checkout. Ticket + QR are only generated once payment succeeds.
    registration, created = Registration.objects.get_or_create(
        event=event, user=request.user, defaults={'status': 'pending_payment'}
    )
    if not created and registration.status == 'cancelled':
        registration.status = 'pending_payment'
        registration.save(update_fields=['status'])

    payment = payment_services.get_or_create_pending_payment(registration)
    return redirect('payments:checkout', payment_id=payment.id)


@login_required
@require_POST
def join_waitlist(request, slug):
    event = get_object_or_404(Event, slug=slug)

    # Same lifecycle rule as registration: a draft, cancelled, or
    # completed event — or one that's already started — can't be
    # joined via the waitlist either. Checked here (not just relying on
    # waitlist_services.join_waitlist's own guard) so the messaging is
    # specific instead of falling through to a generic "already
    # registered" message.
    if not event.is_registration_open:
        messages.error(
            request,
            f"Registration for \"{event.title}\" is closed — it's either "
            "not published yet, cancelled, completed, or already underway."
        )
        return redirect('events:event_detail', slug=slug)

    if not event.is_full:
        messages.info(request, "This event still has open seats — register directly instead.")
        return redirect('events:event_detail', slug=slug)

    entry, created = waitlist_services.join_waitlist(event, request.user)
    if entry is None:
        messages.info(request, "You're already registered for this event.")
    elif created:
        messages.success(request, f"You're on the waitlist — position #{entry.position}.")
    else:
        messages.info(request, f"You're already on the waitlist — position #{entry.position}.")
    return redirect('events:event_detail', slug=slug)


@login_required
@require_POST
def leave_waitlist(request, slug):
    event = get_object_or_404(Event, slug=slug)
    left = waitlist_services.leave_waitlist(event, request.user)
    if left:
        messages.success(request, "You've left the waitlist.")
    return redirect('events:event_detail', slug=slug)


@login_required
def event_waitlist_manage(request, slug):
    """Organizer/staff view of an event's waitlist."""
    event = get_object_or_404(Event, slug=slug)
    if not (request.user == event.organizer or request.user.is_staff_role or request.user.is_super_admin):
        messages.error(request, "You don't have permission to view this event's waitlist.")
        return redirect('events:event_detail', slug=slug)

    waitlist_services.expire_stale_invitations(event)
    entries = event.waitlist_entries.filter(
        status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
    ).select_related('user').order_by('position')
    return render(request, 'events/event_waitlist_manage.html', {'event': event, 'entries': entries})


@login_required
def event_cancel_registration(request, slug):
    event = get_object_or_404(Event, slug=slug)
    registration = get_object_or_404(Registration, event=event, user=request.user)

    if request.method == 'POST':
        registration.status = 'cancelled'
        registration.save(update_fields=['status'])
        waitlist_services.promote_next_waitlisted(event)
        messages.success(request, f"Your registration for {event.title} has been cancelled.")
        return redirect('events:my_registrations')
    return render(request, 'events/registration_confirm_cancel.html', {'registration': registration})


@login_required
def my_registrations(request):
    registrations = (
        Registration.objects.filter(user=request.user)
        .select_related('event', 'event__category')
        .order_by('-registered_at')
    )
    waitlist_entries = (
        WaitlistEntry.objects.filter(
            user=request.user, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
        )
        .select_related('event', 'event__category')
        .order_by('-joined_at')
    )
    return render(request, 'events/my_registrations.html', {
        'registrations': registrations,
        'waitlist_entries': waitlist_entries,
    })


def event_ics(request, slug):
    """Export to Google Calendar (Module 10): a downloadable .ics file.
    Public, same as event_detail — anyone who can see the event can add
    it to their own calendar without needing an account."""
    event = get_object_or_404(Event, slug=slug)
    ics_bytes = build_ics_bytes(event)
    response = HttpResponse(ics_bytes, content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{event.slug}.ics"'
    return response