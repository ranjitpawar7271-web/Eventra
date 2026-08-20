from io import BytesIO
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import OperationalError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from events.models import Event
from users.models import User
from .forms import TicketStatusForm, TicketTypeForm
from .models import CheckInLog, Ticket
from .utils import render_qr_png

# Per spec: Staff, Organizer, Super Admin can scan/manage tickets. Staff and
# Super Admin can do this for any event; an Organizer only for events they
# organize themselves — the same ownership rule already used everywhere
# else event-management touches permissions (event_update, event_participants,
# budget._can_manage_budget), so ticketing doesn't introduce a new, looser
# permission model of its own.


def _can_manage_tickets(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


def _can_view_ticket(user, ticket):
    if not user.is_authenticated:
        return False
    if ticket.registration.user_id == user.id:
        return True
    return _can_manage_tickets(user, ticket.event)


def _ticket_payload(ticket):
    return {
        'ticket_code': ticket.ticket_code,
        'participant': ticket.participant.get_full_name() or ticket.participant.username,
        'ticket_type': ticket.get_ticket_type_display(),
        'status': ticket.get_status_display(),
    }


# --- Participant-facing views -------------------------------------------

@login_required
def my_tickets(request):
    tickets = (
        Ticket.objects.filter(registration__user=request.user)
        .select_related('registration__event', 'registration__event__category')
        .order_by('-issued_at')
    )
    return render(request, 'tickets/my_tickets.html', {'tickets': tickets})


@login_required
def ticket_detail(request, ticket_code):
    ticket = get_object_or_404(
        Ticket.objects.select_related('registration__event', 'registration__user'),
        ticket_code=ticket_code
    )
    if not _can_view_ticket(request.user, ticket):
        messages.error(request, "You don't have permission to view this ticket.")
        return redirect('dashboard:dashboard')

    can_manage = _can_manage_tickets(request.user, ticket.event)
    context = {
        'ticket': ticket,
        'can_manage': can_manage,
    }
    if can_manage:
        context['type_form'] = TicketTypeForm(instance=ticket)
        context['status_form'] = TicketStatusForm(instance=ticket)
    return render(request, 'tickets/ticket_detail.html', context)


@login_required
def ticket_qr_image(request, ticket_code):
    ticket = get_object_or_404(Ticket, ticket_code=ticket_code)
    if not _can_view_ticket(request.user, ticket):
        return HttpResponse(status=403)
    png = render_qr_png(ticket.qr_token)
    return HttpResponse(png, content_type='image/png')


@login_required
def ticket_pdf(request, ticket_code):
    ticket = get_object_or_404(
        Ticket.objects.select_related('registration__event', 'registration__user'),
        ticket_code=ticket_code
    )
    if not _can_view_ticket(request.user, ticket):
        messages.error(request, "You don't have permission to download this ticket.")
        return redirect('dashboard:dashboard')

    pdf_bytes = _build_ticket_pdf(ticket)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{ticket.ticket_code}.pdf"'
    return response


def _build_ticket_pdf(ticket):
    """Renders a single-page, ticket-sized PDF with the QR embedded.
    Kept as a plain function (not a view) so it stays easy to reuse later
    for an "email my ticket" feature without duplicating the layout.
    """
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    event = ticket.event
    participant = ticket.participant

    buffer = BytesIO()
    width, height = A6
    c = canvas.Canvas(buffer, pagesize=A6)

    # Header band
    c.setFillColorRGB(0.09, 0.11, 0.16)
    c.rect(0, height - 24 * mm, width, 24 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(10 * mm, height - 11 * mm, 'Eventra')
    c.setFont('Helvetica', 8)
    c.drawString(10 * mm, height - 18 * mm, 'Admission Ticket')

    c.setFillColorRGB(0, 0, 0)
    y = height - 32 * mm
    c.setFont('Helvetica-Bold', 12)
    c.drawString(10 * mm, y, event.title[:42])
    y -= 7 * mm

    c.setFont('Helvetica', 9)
    c.drawString(10 * mm, y, f"When: {event.start_date.strftime('%b %d, %Y - %I:%M %p')}")
    y -= 5.5 * mm
    c.drawString(10 * mm, y, f"Where: {event.location[:48]}")
    y -= 5.5 * mm
    c.drawString(10 * mm, y, f"Attendee: {participant.get_full_name() or participant.username}")
    y -= 5.5 * mm
    c.drawString(10 * mm, y, f"Ticket Type: {ticket.get_ticket_type_display()}")
    y -= 5.5 * mm
    c.drawString(10 * mm, y, f"Status: {ticket.get_status_display()}")

    # QR code, embedded from the same signed token used by the on-screen view.
    qr_png = render_qr_png(ticket.qr_token, box_size=6, border=1)
    qr_reader = ImageReader(BytesIO(qr_png))
    qr_size = 42 * mm
    qr_x = (width - qr_size) / 2
    qr_y = 12 * mm
    c.drawImage(qr_reader, qr_x, qr_y, width=qr_size, height=qr_size)

    c.setFont('Helvetica', 7)
    c.drawCentredString(width / 2, qr_y - 5 * mm, ticket.ticket_code)
    c.setFont('Helvetica-Oblique', 6.5)
    c.drawCentredString(width / 2, 4 * mm, 'Present this QR code at the door for scanning.')

    c.showPage()
    c.save()
    return buffer.getvalue()


# --- Organizer/Staff/Super Admin management views ------------------------

@login_required
def ticket_type_update(request, ticket_code):
    ticket = get_object_or_404(Ticket, ticket_code=ticket_code)
    if not _can_manage_tickets(request.user, ticket.event):
        messages.error(request, "You don't have permission to update this ticket.")
        return redirect('tickets:ticket_detail', ticket_code=ticket_code)

    if request.method == 'POST':
        form = TicketTypeForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            messages.success(request, "Ticket type updated.")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect('tickets:ticket_detail', ticket_code=ticket_code)


@login_required
def ticket_status_update(request, ticket_code):
    ticket = get_object_or_404(Ticket, ticket_code=ticket_code)
    if not _can_manage_tickets(request.user, ticket.event):
        messages.error(request, "You don't have permission to update this ticket.")
        return redirect('tickets:ticket_detail', ticket_code=ticket_code)

    if ticket.status == Ticket.STATUS_CHECKED_IN:
        messages.error(
            request,
            "This ticket has already been checked in — cancel/refund isn't available after check-in."
        )
        return redirect('tickets:ticket_detail', ticket_code=ticket_code)

    if request.method == 'POST':
        form = TicketStatusForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            messages.success(request, "Ticket status updated.")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect('tickets:ticket_detail', ticket_code=ticket_code)


@login_required
def scanner_page(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_tickets(request.user, event):
        messages.error(request, "You don't have permission to scan tickets for this event.")
        return redirect('events:event_detail', slug=slug)
    return render(request, 'tickets/scanner.html', {'event': event})


@login_required
def event_checkin_logs(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_tickets(request.user, event):
        messages.error(request, "You don't have permission to view attendance for this event.")
        return redirect('events:event_detail', slug=slug)

    logs = (
        CheckInLog.objects.filter(event=event)
        .select_related('ticket', 'ticket__registration__user', 'scanned_by')
        .order_by('-scanned_at')
    )
    stats = _attendance_stats(event)

    context = {
        'event': event,
        'logs': logs,
        **stats,
    }
    return render(request, 'tickets/checkin_logs.html', context)


def _attendance_stats(event):
    tickets = Ticket.objects.filter(registration__event=event)
    logs = CheckInLog.objects.filter(event=event)
    registered = tickets.exclude(status__in=[Ticket.STATUS_CANCELLED, Ticket.STATUS_REFUNDED]).count()
    checked_in = tickets.filter(status=Ticket.STATUS_CHECKED_IN).count()
    not_arrived = max(registered - checked_in, 0)
    return {
        'total_tickets': tickets.count(),
        'registered_count': registered,
        'checked_in_count': checked_in,
        'issued_count': not_arrived,
        'inactive_count': tickets.filter(status__in=[Ticket.STATUS_CANCELLED, Ticket.STATUS_REFUNDED]).count(),
        'duplicate_attempts': logs.filter(result=CheckInLog.RESULT_DUPLICATE).count(),
        'invalid_attempts': logs.filter(result=CheckInLog.RESULT_INVALID).count(),
        'attendance_rate': round((checked_in / registered) * 100, 1) if registered else 0,
    }


@login_required
def event_checkin_stats_json(request, slug):
    """Polled by checkin_logs.html to keep the stat cards + recent scans
    live without a full page reload while staff are actively scanning
    at the door."""
    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_tickets(request.user, event):
        return JsonResponse({'error': 'forbidden'}, status=403)

    stats = _attendance_stats(event)
    recent = list(
        CheckInLog.objects.filter(event=event)
        .select_related('ticket__registration__user', 'scanned_by')
        .order_by('-scanned_at')[:10]
        .values('result', 'detail', 'scanned_at')
    )
    for r in recent:
        r['scanned_at'] = timezone.localtime(r['scanned_at']).strftime('%I:%M:%S %p')
    return JsonResponse({'stats': stats, 'recent': recent})


@login_required
def event_checkin_logs_export(request, slug):
    import csv

    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_tickets(request.user, event):
        messages.error(request, "You don't have permission to export attendance for this event.")
        return redirect('events:event_detail', slug=slug)

    logs = CheckInLog.objects.filter(event=event).select_related('ticket__registration__user', 'scanned_by').order_by('scanned_at')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{event.slug}-attendance.csv"'
    writer = csv.writer(response)
    writer.writerow(['Time', 'Ticket Code', 'Attendee', 'Result', 'Scanned By', 'Detail'])
    for log in logs:
        writer.writerow([
            log.scanned_at.strftime('%Y-%m-%d %H:%M:%S'),
            log.ticket.ticket_code if log.ticket else '—',
            (log.ticket.participant.get_full_name() or log.ticket.participant.username) if log.ticket else '—',
            log.get_result_display(),
            (log.scanned_by.get_full_name() or log.scanned_by.username) if log.scanned_by else '—',
            log.detail,
        ])
    return response


# --- Scan endpoints (AJAX, called from scanner.html) ----------------------

def _process_scan(request, event, action):
    token = (request.POST.get('token') or '').strip()
    if not token:
        return JsonResponse(
            {'success': False, 'result': 'invalid', 'message': 'No QR data received.'}, status=400
        )

    handler = _handle_checkin if action == 'checkin' else _handle_checkout

    # The whole scan — resolving the token, the event-match check, and
    # the handler's own status transition — is retried as one unit on a
    # transient database lock error. SQLite in particular can report
    # cross-connection contention as an immediate error rather than
    # always waiting, regardless of a configured busy timeout, so even
    # the read in Ticket.resolve_token() below can occasionally hit
    # this. A short bounded retry absorbs that instead of surfacing a
    # raw error to a scan that would very likely succeed a moment
    # later — it does not change the actual duplicate-check-in logic
    # inside the handler in any way.
    attempts = 5
    for attempt in range(1, attempts + 1):
        try:
            return _resolve_and_handle_scan(request, event, token, handler)
        except OperationalError:
            if attempt == attempts:
                break
            time.sleep(0.05 * attempt)

    # Every attempt hit a transient DB error — fail safe, no stack trace,
    # nothing recorded as a successful check-in/out for this attempt.
    CheckInLog.objects.create(
        event=event, ticket=None, scanned_by=request.user,
        result=CheckInLog.RESULT_INVALID,
        detail="Scan couldn't be processed due to a temporary system delay — please rescan."
    )
    return JsonResponse({
        'success': False, 'result': 'invalid',
        'message': "Couldn't process the scan right now — please try again.",
    })


def _resolve_and_handle_scan(request, event, token, handler):
    ticket = Ticket.resolve_token(token)

    if ticket is None:
        CheckInLog.objects.create(
            event=event, ticket=None, scanned_by=request.user,
            result=CheckInLog.RESULT_INVALID, detail="Unrecognized or tampered QR code."
        )
        return JsonResponse({
            'success': False, 'result': 'invalid',
            'message': "This QR code isn't a valid Eventra ticket.",
        })

    if ticket.event_id != event.id:
        CheckInLog.objects.create(
            event=event, ticket=ticket, scanned_by=request.user,
            result=CheckInLog.RESULT_INVALID,
            detail=f"Ticket is for '{ticket.event.title}', not this event."
        )
        return JsonResponse({
            'success': False, 'result': 'invalid',
            'message': f"This ticket is for a different event ({ticket.event.title}).",
        })

    return handler(request, event, ticket)




def _handle_checkin(request, event, ticket):
    """The critical section: read-then-transition a ticket's status to
    CHECKED_IN. Two scanners hitting this for the same ticket at almost
    the same instant is the exact race this function has to close — see
    the module-level note below for why it's implemented this way.
    """
    with transaction.atomic():
        # Lock this ticket's row for the rest of the transaction. On a
        # database that honors row locks (Postgres/MySQL — a typical
        # production choice for this project), a second concurrent
        # request for the *same* ticket blocks here until the first
        # request's transaction commits, then this SELECT re-reads the
        # now-updated row instead of acting on stale data.
        ticket = Ticket.objects.select_for_update().select_related(
            'registration', 'registration__event', 'registration__user'
        ).get(pk=ticket.pk)

        if ticket.status == Ticket.STATUS_CHECKED_IN:
            when = timezone.localtime(ticket.checked_in_at).strftime('%I:%M %p') if ticket.checked_in_at else 'earlier'
            who = (ticket.checked_in_by.get_full_name() or ticket.checked_in_by.username) if ticket.checked_in_by else 'staff'
            detail = f"Already checked in at {when} by {who}."
            CheckInLog.objects.create(
                event=event, ticket=ticket, scanned_by=request.user,
                result=CheckInLog.RESULT_DUPLICATE, detail=detail
            )
            return JsonResponse({
                'success': False, 'result': 'duplicate', 'message': detail,
                'ticket': _ticket_payload(ticket),
            })

        if not ticket.is_usable:
            detail = f"Ticket is {ticket.get_status_display()} and cannot be checked in."
            CheckInLog.objects.create(
                event=event, ticket=ticket, scanned_by=request.user,
                result=CheckInLog.RESULT_INVALID, detail=detail
            )
            return JsonResponse({'success': False, 'result': 'invalid', 'message': detail})

        # The row lock above (select_for_update) is what makes a second
        # request block and re-read on Postgres/MySQL. But this project's
        # dev/test database is SQLite, which has no row-level locking at
        # all — Django silently drops the "FOR UPDATE" clause there, so
        # the SELECT above never blocks anyone on that backend. The
        # UPDATE ... WHERE below is what actually guarantees correctness
        # on *every* backend: a single UPDATE statement conditioned on
        # the status we just read is atomic in any SQL database
        # regardless of locking support, so if two requests race, only
        # the one whose WHERE clause still matches can succeed — the
        # loser's `updated` count comes back 0, not an error and not a
        # second "success".
        now = timezone.now()
        updated = Ticket.objects.filter(pk=ticket.pk, status=ticket.status).update(
            status=Ticket.STATUS_CHECKED_IN, checked_in_at=now, checked_in_by=request.user,
        )
        if not updated:
            # Lost the race between our read and this write.
            ticket.refresh_from_db()
            when = timezone.localtime(ticket.checked_in_at).strftime('%I:%M %p') if ticket.checked_in_at else 'earlier'
            who = (ticket.checked_in_by.get_full_name() or ticket.checked_in_by.username) if ticket.checked_in_by else 'staff'
            detail = f"Already checked in at {when} by {who}."
            CheckInLog.objects.create(
                event=event, ticket=ticket, scanned_by=request.user,
                result=CheckInLog.RESULT_DUPLICATE, detail=detail
            )
            return JsonResponse({
                'success': False, 'result': 'duplicate', 'message': detail,
                'ticket': _ticket_payload(ticket),
            })

        # Reflect the change on the in-memory object (the queryset
        # `.update()` above doesn't touch it) so the log/payload below
        # and the notification after this block see the right status.
        ticket.status = Ticket.STATUS_CHECKED_IN
        ticket.checked_in_at = now
        ticket.checked_in_by = request.user

        detail = f"Checked in {ticket.participant.get_full_name() or ticket.participant.username}."
        CheckInLog.objects.create(
            event=event, ticket=ticket, scanned_by=request.user,
            result=CheckInLog.RESULT_CHECKED_IN, detail=detail
        )

    # Notification sent after the transaction commits — no reason to hold
    # the row lock (on backends that have one) through a step that isn't
    # part of the status transition itself.
    from workflow.models import Notification
    Notification.notify(
        ticket.participant,
        f"You're checked in for \"{event.title}\". Enjoy the event!",
        link=ticket.get_absolute_url(),
        notification_type=Notification.TYPE_CHECKIN,
        related_event=event,
        dedupe_key=f'checkin-confirmed-{ticket.pk}',
        email=False,  # a door check-in doesn't need an email round-trip; in-app is enough
    )

    return JsonResponse({
        'success': True, 'result': 'checked_in', 'message': detail,
        'ticket': _ticket_payload(ticket),
    })


def _handle_checkout(request, event, ticket):
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().select_related(
            'registration', 'registration__event', 'registration__user'
        ).get(pk=ticket.pk)

        if ticket.status != Ticket.STATUS_CHECKED_IN:
            detail = "Ticket hasn't been checked in yet, so it can't be checked out."
            CheckInLog.objects.create(
                event=event, ticket=ticket, scanned_by=request.user,
                result=CheckInLog.RESULT_INVALID, detail=detail
            )
            return JsonResponse({'success': False, 'result': 'invalid', 'message': detail})

        if ticket.checked_out_at:
            when = timezone.localtime(ticket.checked_out_at).strftime('%I:%M %p')
            detail = f"Already checked out at {when}."
            CheckInLog.objects.create(
                event=event, ticket=ticket, scanned_by=request.user,
                result=CheckInLog.RESULT_DUPLICATE, detail=detail
            )
            return JsonResponse({
                'success': False, 'result': 'duplicate', 'message': detail,
                'ticket': _ticket_payload(ticket),
            })

        # Same conditional-UPDATE guard as check-in, for the same reason:
        # `checked_out_at IS NULL` in the WHERE clause is what actually
        # closes the race on every backend, not just the row lock above.
        now = timezone.now()
        updated = Ticket.objects.filter(pk=ticket.pk, checked_out_at__isnull=True).update(
            checked_out_at=now, checked_out_by=request.user,
        )
        if not updated:
            ticket.refresh_from_db()
            when = timezone.localtime(ticket.checked_out_at).strftime('%I:%M %p') if ticket.checked_out_at else 'earlier'
            detail = f"Already checked out at {when}."
            CheckInLog.objects.create(
                event=event, ticket=ticket, scanned_by=request.user,
                result=CheckInLog.RESULT_DUPLICATE, detail=detail
            )
            return JsonResponse({
                'success': False, 'result': 'duplicate', 'message': detail,
                'ticket': _ticket_payload(ticket),
            })

        ticket.checked_out_at = now
        ticket.checked_out_by = request.user

        detail = f"Checked out {ticket.participant.get_full_name() or ticket.participant.username}."
        CheckInLog.objects.create(
            event=event, ticket=ticket, scanned_by=request.user,
            result=CheckInLog.RESULT_CHECKED_OUT, detail=detail
        )
    return JsonResponse({
        'success': True, 'result': 'checked_out', 'message': detail,
        'ticket': _ticket_payload(ticket),
    })


@login_required
@require_POST
def check_in(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_tickets(request.user, event):
        return JsonResponse(
            {'success': False, 'message': "You don't have permission to scan tickets for this event."},
            status=403
        )
    return _process_scan(request, event, 'checkin')


@login_required
@require_POST
def check_out(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if not _can_manage_tickets(request.user, event):
        return JsonResponse(
            {'success': False, 'message': "You don't have permission to scan tickets for this event."},
            status=403
        )
    return _process_scan(request, event, 'checkout')