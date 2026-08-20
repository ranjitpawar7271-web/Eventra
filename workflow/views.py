import calendar as calendar_module
from collections import defaultdict
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from events.models import Event
from staff.models import ShiftAssignment
from users.models import User
from users.permissions import role_required
from venues.models import VenueBooking

from .forms import ApprovalDecisionForm, BroadcastForm, WorkflowSettingsForm
from .models import ApprovalStep, Notification, WorkflowSettings


APPROVAL_ROLES = (User.SUPER_ADMIN, User.STAFF)


# ============================================================================
# APPROVALS
# ============================================================================

@role_required(*APPROVAL_ROLES)
def approval_list(request):
    pending = (
        ApprovalStep.objects
        .filter(status=ApprovalStep.STATUS_PENDING)
        .select_related('content_type', 'requested_by')
        .order_by('requested_at')
    )

    decided = (
        ApprovalStep.objects
        .exclude(status=ApprovalStep.STATUS_PENDING)
        .select_related(
            'content_type',
            'requested_by',
            'decided_by',
        )
        .order_by('-decided_at')[:20]
    )

    return render(
        request,
        'workflow/approval_list.html',
        {
            'pending_steps': pending,
            'decided_steps': decided,
            'form': ApprovalDecisionForm(),
        },
    )


@role_required(*APPROVAL_ROLES)
def approval_decide(request, pk, action):
    step = get_object_or_404(
        ApprovalStep,
        pk=pk,
        status=ApprovalStep.STATUS_PENDING,
    )

    if request.method != 'POST' or action not in ('approve', 'reject'):
        return redirect('workflow:approval_list')

    form = ApprovalDecisionForm(request.POST)

    comment = (
        form.data.get('comment', '')
        if form.is_valid()
        else ''
    )

    target_label = str(step.content_object)

    if action == 'approve':
        step.approve(
            request.user,
            comment=comment,
        )
        messages.success(
            request,
            f"Approved: {target_label}",
        )

    else:
        step.reject(
            request.user,
            comment=comment,
        )
        messages.success(
            request,
            f"Rejected: {target_label}",
        )

    return redirect('workflow:approval_list')


# ============================================================================
# WORKFLOW SETTINGS
# ============================================================================

@role_required(*APPROVAL_ROLES)
def workflow_settings_view(request):
    settings_obj = WorkflowSettings.get_solo()

    if request.method == 'POST':
        form = WorkflowSettingsForm(
            request.POST,
            instance=settings_obj,
        )

        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()

            messages.success(
                request,
                "Workflow settings updated.",
            )

            return redirect('workflow:settings')

    else:
        form = WorkflowSettingsForm(
            instance=settings_obj,
        )

    return render(
        request,
        'workflow/settings.html',
        {
            'form': form,
        },
    )


# ============================================================================
# ANNOUNCEMENTS
# ============================================================================

@role_required(*APPROVAL_ROLES)
def announce(request):
    if request.method == 'POST':
        form = BroadcastForm(request.POST)

        if form.is_valid():
            message = form.cleaned_data['message']
            link = form.cleaned_data['link']

            recipients = User.objects.exclude(
                pk=request.user.pk
            )

            for recipient in recipients:
                Notification.notify(
                    recipient,
                    message,
                    link=link,
                    notification_type=Notification.TYPE_ANNOUNCEMENT,
                )

            messages.success(
                request,
                f"Announcement sent to {recipients.count()} users.",
            )

            return redirect('workflow:announce')

    else:
        form = BroadcastForm()

    return render(
        request,
        'workflow/announce.html',
        {
            'form': form,
        },
    )


# ============================================================================
# NOTIFICATIONS
# ============================================================================

@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        user=request.user
    )

    return render(
        request,
        'workflow/notification_list.html',
        {
            'notifications': notifications,
        },
    )


@login_required
def notification_read(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user,
    )

    if not notification.is_read:
        notification.is_read = True

        notification.save(
            update_fields=['is_read']
        )

    if notification.link:
        return redirect(notification.link)

    return redirect('workflow:notification_list')


@login_required
def notifications_mark_all_read(request):
    if request.method == 'POST':
        Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True)

    return redirect(
        request.POST.get('next')
        or 'workflow:notification_list'
    )


# ============================================================================
# CALENDAR — VISIBLE EVENTS
# ============================================================================

def _visible_events(user):
    qs = Event.objects.select_related(
        'category',
        'venue',
    )

    # Super Admin and Staff can see every event.
    if user.is_super_admin or user.is_staff_role:
        return qs

    # Organizers can see:
    # - published events
    # - their own events
    if user.can_manage_events:
        from django.db.models import Q

        return qs.filter(
            Q(status='published') |
            Q(organizer=user)
        )

    # Participants only see events they have
    # actually registered for and confirmed.
    return qs.filter(
        registrations__user=user,
        registrations__status='confirmed',
    ).distinct()


# ============================================================================
# CALENDAR — VISIBLE VENUE BOOKINGS
# ============================================================================

def _visible_bookings(user):
    qs = (
        VenueBooking.objects
        .filter(status='confirmed')
        .select_related(
            'venue',
            'event',
        )
    )

    if user.is_super_admin or user.is_staff_role:
        return qs

    from django.db.models import Q

    return qs.filter(
        Q(booked_by=user) |
        Q(event__organizer=user)
    )


# ============================================================================
# CALENDAR — VISIBLE STAFF SHIFTS
# ============================================================================

def _visible_shifts(user):
    qs = (
        ShiftAssignment.objects
        .filter(status='assigned')
        .select_related(
            'staff__user',
            'event',
        )
    )

    if user.is_super_admin or user.is_staff_role:
        return qs

    from django.db.models import Q

    return qs.filter(
        Q(staff__user=user) |
        Q(event__organizer=user)
    )


# ============================================================================
# CALENDAR — VISIBLE TASKS
# ============================================================================

def _visible_tasks(user):
    """
    Event checklist/task deadlines.
    """

    from tasks.models import Task

    qs = (
        Task.objects
        .exclude(due_date__isnull=True)
        .select_related('event')
    )

    if user.is_super_admin or user.is_staff_role:
        return qs

    from django.db.models import Q

    return qs.filter(
        Q(event__organizer=user) |
        Q(assigned_to=user)
    )


# ============================================================================
# CALENDAR — COLLECT AGENDA
# ============================================================================

def _collect_agenda(user, range_start, range_end_exclusive):
    """
    Returns {date: [items]} for everything visible to `user`
    whose start/due date falls within the requested range.

    Event dates intentionally use event.start_date.date()
    because the calendar test and Event model treat the stored
    event date as the calendar date.
    """
    agenda = defaultdict(list)

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------
    #
    # NOTE ON DATE HANDLING:
    # Event.start_date is a timezone-aware DateTimeField. Everywhere else
    # in this function (and in calendar_view()) an event's "calendar day"
    # is defined as `event.start_date.date()` — the date component of the
    # stored aware datetime itself, not its localtime()-converted date.
    #
    # A plain `start_date__date__gte/lt` lookup does NOT match that: with
    # USE_TZ=True, Django's `__date` lookup converts the datetime to the
    # *current* time zone (settings.TIME_ZONE) before extracting the date.
    # Since TIME_ZONE is 'Asia/Kolkata' (UTC+5:30), any event whose UTC
    # time falls between 18:30 and 23:59 lands on the *next* local day,
    # so the SQL-side date no longer agrees with `start_date.date()` used
    # for the agenda key below — the event silently disappears from the
    # range it should belong to.
    #
    # To keep one consistent interpretation throughout, filter using an
    # explicit UTC datetime range that corresponds to `start_date.date()`
    # rather than letting the ORM re-interpret the date in local time.
    range_start_dt = datetime.combine(
        range_start, datetime.min.time(), tzinfo=dt_timezone.utc
    )
    range_end_dt = datetime.combine(
        range_end_exclusive, datetime.min.time(), tzinfo=dt_timezone.utc
    )

    events = _visible_events(user).filter(
        start_date__gte=range_start_dt,
        start_date__lt=range_end_dt,
    )

    for event in events:
        event_date = event.start_date.date()

        agenda[event_date].append({
            'time': timezone.localtime(
                event.start_date
            ).strftime('%H:%M'),
            'label': event.title,
            'url': event.get_absolute_url(),
            'type': 'event',
            'badge': event.get_status_display(),
        })

    # ------------------------------------------------------------------
    # VENUE BOOKINGS
    # ------------------------------------------------------------------

    bookings = _visible_bookings(user).filter(
        start_datetime__date__gte=range_start,
        start_datetime__date__lt=range_end_exclusive,
    )

    for booking in bookings:
        booking_date = booking.start_datetime.date()

        agenda[booking_date].append({
            'time': timezone.localtime(
                booking.start_datetime
            ).strftime('%H:%M'),
            'label': f"Venue: {booking.venue.name}",
            'url': booking.venue.get_absolute_url(),
            'type': 'booking',
            'badge': 'Booking',
        })

    # ------------------------------------------------------------------
    # STAFF SHIFTS
    # ------------------------------------------------------------------

    shifts = _visible_shifts(user).filter(
        start_datetime__date__gte=range_start,
        start_datetime__date__lt=range_end_exclusive,
    )

    for shift in shifts:
        shift_date = shift.start_datetime.date()

        agenda[shift_date].append({
            'time': timezone.localtime(
                shift.start_datetime
            ).strftime('%H:%M'),
            'label': (
                f"Shift: "
                f"{shift.staff.user.get_full_name() or shift.staff.user.username} "
                f"— {shift.title}"
            ),
            'url': reverse(
                'staff:staff_detail',
                kwargs={'pk': shift.staff.pk},
            ),
            'type': 'shift',
            'badge': 'Staff',
        })

    # ------------------------------------------------------------------
    # TASK DEADLINES
    # ------------------------------------------------------------------

    tasks = _visible_tasks(user).filter(
        due_date__gte=range_start,
        due_date__lt=range_end_exclusive,
    )

    for task in tasks:
        agenda[task.due_date].append({
            'time': '23:59',
            'label': f"Deadline: {task.title}",
            'url': reverse(
                'tasks:task_detail',
                kwargs={'pk': task.pk},
            ),
            'type': 'task',
            'badge': task.get_priority_display(),
        })

    # ------------------------------------------------------------------
    # SORT ITEMS BY TIME
    # ------------------------------------------------------------------

    for items in agenda.values():
        items.sort(
            key=lambda item: item['time']
        )

    return agenda
    # ========================================================================
    # VENUE BOOKINGS
    # ========================================================================

    bookings = _visible_bookings(user).filter(
        start_datetime__date__gte=range_start,
        start_datetime__date__lt=range_end_exclusive,
    )

    for booking in bookings:

        booking_start = timezone.localtime(
            booking.start_datetime
        )

        booking_date = booking_start.date()

        agenda[booking_date].append(
            {
                'time': booking_start.strftime('%H:%M'),
                'label': f"Venue: {booking.venue.name}",
                'url': booking.venue.get_absolute_url(),
                'type': 'booking',
                'badge': 'Booking',
            }
        )

    # ========================================================================
    # STAFF SHIFTS
    # ========================================================================

    shifts = _visible_shifts(user).filter(
        start_datetime__date__gte=range_start,
        start_datetime__date__lt=range_end_exclusive,
    )

    for shift in shifts:

        shift_start = timezone.localtime(
            shift.start_datetime
        )

        shift_date = shift_start.date()

        staff_name = (
            shift.staff.user.get_full_name()
            or shift.staff.user.username
        )

        agenda[shift_date].append(
            {
                'time': shift_start.strftime('%H:%M'),
                'label': (
                    f"Shift: {staff_name} — {shift.title}"
                ),
                'url': reverse(
                    'staff:staff_detail',
                    kwargs={
                        'pk': shift.staff.pk,
                    },
                ),
                'type': 'shift',
                'badge': 'Staff',
            }
        )

    # ========================================================================
    # TASK DEADLINES
    # ========================================================================

    tasks = _visible_tasks(user).filter(
        due_date__gte=range_start,
        due_date__lt=range_end_exclusive,
    )

    for task in tasks:

        agenda[task.due_date].append(
            {
                'time': '23:59',
                'label': f"Deadline: {task.title}",
                'url': reverse(
                    'tasks:task_detail',
                    kwargs={
                        'pk': task.pk,
                    },
                ),
                'type': 'task',
                'badge': task.get_priority_display(),
            }
        )

    # ========================================================================
    # SORT AGENDA ITEMS
    # ========================================================================

    for items in agenda.values():
        items.sort(
            key=lambda item: item['time']
        )

    return agenda


# ============================================================================
# CALENDAR VIEW
# ============================================================================

@login_required
def calendar_view(request):

    view = request.GET.get(
        'view',
        'month',
    )

    # Only allow supported calendar modes.
    if view not in (
        'month',
        'week',
        'day',
    ):
        view = 'month'

    # Read requested date.
    # If no valid date was supplied, use today's local date.
    anchor = (
        parse_date(
            request.GET.get('date', '')
        )
        or timezone.localdate()
    )

    # ========================================================================
    # MONTH VIEW
    # ========================================================================

    if view == 'month':

        first_of_month = anchor.replace(
            day=1
        )

        _, days_in_month = calendar_module.monthrange(
            anchor.year,
            anchor.month,
        )

        range_start = first_of_month

        range_end_exclusive = (
            first_of_month
            + timedelta(days=days_in_month)
        )

        agenda = _collect_agenda(
            request.user,
            range_start,
            range_end_exclusive,
        )

        weeks = (
            calendar_module
            .Calendar(firstweekday=0)
            .monthdayscalendar(
                anchor.year,
                anchor.month,
            )
        )

        grid = []

        for week in weeks:

            week_row = []

            for day_num in week:

                if day_num == 0:
                    week_row.append(None)

                else:
                    day_date = anchor.replace(
                        day=day_num
                    )

                    week_row.append(
                        {
                            'date': day_date,
                            'items': agenda.get(
                                day_date,
                                [],
                            ),
                        }
                    )

            grid.append(week_row)

        prev_anchor = (
            first_of_month
            - timedelta(days=1)
        ).replace(day=1)

        next_anchor = range_end_exclusive

        context = {
            'view': 'month',
            'anchor': anchor,
            'grid': grid,
            'month_label': anchor.strftime(
                '%B %Y'
            ),
            'prev_date': prev_anchor.isoformat(),
            'next_date': next_anchor.isoformat(),
        }

    # ========================================================================
    # WEEK VIEW
    # ========================================================================

    elif view == 'week':

        range_start = (
            anchor
            - timedelta(
                days=anchor.weekday()
            )
        )

        range_end_exclusive = (
            range_start
            + timedelta(days=7)
        )

        agenda = _collect_agenda(
            request.user,
            range_start,
            range_end_exclusive,
        )

        days = [
            {
                'date': (
                    range_start
                    + timedelta(days=i)
                ),
                'items': agenda.get(
                    range_start
                    + timedelta(days=i),
                    [],
                ),
            }
            for i in range(7)
        ]

        context = {
            'view': 'week',
            'anchor': anchor,
            'days': days,
            'month_label': (
                f"{range_start.strftime('%b %d')}"
                f" – "
                f"{(range_end_exclusive - timedelta(days=1)).strftime('%b %d, %Y')}"
            ),
            'prev_date': (
                range_start
                - timedelta(days=7)
            ).isoformat(),
            'next_date': (
                range_end_exclusive
            ).isoformat(),
        }

    # ========================================================================
    # DAY VIEW
    # ========================================================================

    else:

        range_start = anchor

        range_end_exclusive = (
            anchor
            + timedelta(days=1)
        )

        agenda = _collect_agenda(
            request.user,
            range_start,
            range_end_exclusive,
        )

        context = {
            'view': 'day',
            'anchor': anchor,
            'items': agenda.get(
                anchor,
                [],
            ),
            'month_label': anchor.strftime(
                '%A, %b %d, %Y'
            ),
            'prev_date': (
                anchor
                - timedelta(days=1)
            ).isoformat(),
            'next_date': (
                anchor
                + timedelta(days=1)
            ).isoformat(),
        }

    # ========================================================================
    # COMMON CONTEXT
    # ========================================================================

    context['today'] = (
        timezone.localdate().isoformat()
    )

    return render(
        request,
        'workflow/calendar.html',
        context,
    )