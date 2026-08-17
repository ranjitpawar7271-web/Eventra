"""
Report data builders.

Each `build_*_report(events_qs, event, user, request)` function returns a
plain dict shaped like:

    {
        'title': str,
        'subtitle': str,                 # "All Events" / "My Events" / event title
        'summary': [(label, value), ...] # shown as stat cards / a summary block
        'columns': [str, ...],
        'currency_columns': {int, ...},  # column indexes to prefix with a currency mark
        'rows': [[cell, ...], ...],      # numeric cells stay numeric (Decimal/int/float)
    }

Keeping the data layer separate from rendering means the HTML view, and the
CSV/XLSX/PDF exporters in export.py, all work off the exact same numbers —
there's only one place that decides what a report contains.

`events_qs` is always the Event queryset already scoped to what the
requesting user is allowed to see (see views._scoped_events): every event
they organize, or every event platform-wide for Staff/Super Admin. `event`
is None for an aggregate/system report, or a single Event when drilling
into one event's report.
"""
from datetime import datetime, time

from django.db.models import Avg, Count, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from budget.models import EventBudget, Expense, RevenueEntry
from events.models import Registration, WaitlistEntry
from resources.models import Resource, ResourceAllocation
from staff.models import AttendanceRecord, ShiftAssignment, StaffProfile
from tickets.models import CheckInLog, Ticket
from vendors.models import VendorContract, VendorPayment, VendorProfile, VendorRating


def _subtitle(event, user):
    if event is not None:
        return event.title
    if user.is_super_admin or user.is_staff_role:
        return "All Events (System-wide)"
    return "My Events"


def _display_name(person):
    if person is None:
        return "—"
    return person.get_full_name() or person.username


# --- 1. Attendance report (Module 7: CheckInLog) --------------------------

def build_attendance_report(events_qs, event, user, request):
    logs = (
        CheckInLog.objects.filter(event__in=events_qs)
        .select_related('event', 'ticket', 'ticket__registration__user', 'scanned_by')
        .order_by('-scanned_at')
    )
    total_tickets = Ticket.objects.filter(registration__event__in=events_qs).count()
    tickets_used = Ticket.objects.filter(registration__event__in=events_qs, status=Ticket.STATUS_CHECKED_IN).count()
    tickets_unused = Ticket.objects.filter(registration__event__in=events_qs, status=Ticket.STATUS_ISSUED).count()

    summary = [
        ('Total Tickets Issued', total_tickets),
        ('Tickets Used (Checked In)', tickets_used),
        ('Tickets Unused', tickets_unused),
        ('Total Scans', logs.count()),
        ('Checked In', logs.filter(result=CheckInLog.RESULT_CHECKED_IN).count()),
        ('Checked Out', logs.filter(result=CheckInLog.RESULT_CHECKED_OUT).count()),
        ('Duplicate Attempts', logs.filter(result=CheckInLog.RESULT_DUPLICATE).count()),
        ('Invalid Scans', logs.filter(result=CheckInLog.RESULT_INVALID).count()),
    ]
    columns = ['Event', 'Time', 'Ticket Code', 'Attendee', 'Result', 'Scanned By', 'Detail']
    rows = [
        [
            log.event.title,
            timezone.localtime(log.scanned_at).strftime('%Y-%m-%d %H:%M:%S'),
            log.ticket.ticket_code if log.ticket else '—',
            _display_name(log.ticket.participant) if log.ticket else '—',
            log.get_result_display(),
            _display_name(log.scanned_by),
            log.detail,
        ]
        for log in logs[:2000]  # sane cap so a huge event doesn't blow up an export
    ]
    return {
        'title': 'Attendance Report',
        'subtitle': _subtitle(event, user),
        'summary': summary,
        'columns': columns,
        'currency_columns': set(),
        'rows': rows,
    }


# --- 2. Revenue / Expense / Profit-Loss report (Module 6) -----------------

def build_financial_report(events_qs, event, user, request):
    budgets = (
        EventBudget.objects.filter(event__in=events_qs)
        .select_related('event')
        .order_by('-event__start_date')
    )
    columns = ['Event', 'Estimated Budget', 'Total Expenses', 'Total Revenue', 'Profit / Loss', 'Variance', 'Budget Status']
    rows = []
    total_estimated = total_expenses = total_revenue = 0
    for b in budgets:
        total_estimated += b.estimated_budget
        total_expenses += b.total_expenses
        total_revenue += b.total_revenue
        rows.append([
            b.event.title,
            b.estimated_budget,
            b.total_expenses,
            b.total_revenue,
            b.profit_or_loss,
            b.variance,
            'Over Budget' if b.is_over_budget else 'Within Budget',
        ])
    total_profit = total_revenue - total_expenses

    summary = [
        ('Events with a Budget', budgets.count()),
        ('Total Estimated Budget', total_estimated),
        ('Total Expenses', total_expenses),
        ('Total Revenue', total_revenue),
        ('Net Profit / Loss', total_profit),
    ]
    return {
        'title': 'Revenue / Expense / Profit-Loss Report',
        'subtitle': _subtitle(event, user),
        'summary': summary,
        'columns': columns,
        'currency_columns': {1, 2, 3, 4, 5},
        'rows': rows,
    }


# --- 3. Event summary report (events + venues + budget) -------------------

def build_event_summary_report(events_qs, event, user, request):
    events = events_qs.select_related('category', 'organizer', 'venue', 'budget').order_by('-start_date')
    columns = [
        'Event', 'Category', 'Organizer', 'Venue', 'Start Date', 'Status',
        'Capacity', 'Registered', 'Seats Left',
        'Estimated Budget', 'Total Expenses', 'Total Revenue', 'Profit / Loss',
    ]
    rows = []
    total_capacity = 0
    total_registered = 0
    for e in events:
        budget = getattr(e, 'budget', None)
        total_capacity += e.capacity
        total_registered += e.seats_taken
        rows.append([
            e.title,
            e.category.name if e.category else '—',
            _display_name(e.organizer),
            e.venue.name if e.venue else e.location,
            timezone.localtime(e.start_date).strftime('%Y-%m-%d %H:%M'),
            e.get_status_display(),
            e.capacity,
            e.seats_taken,
            e.seats_left,
            budget.estimated_budget if budget else 0,
            budget.total_expenses if budget else 0,
            budget.total_revenue if budget else 0,
            budget.profit_or_loss if budget else 0,
        ])

    summary = [
        ('Total Events', events.count()),
        ('Total Capacity', total_capacity),
        ('Total Registered', total_registered),
        ('Confirmed Registrations', Registration.objects.filter(event__in=events_qs, status='confirmed').count()),
        ('Cancelled Registrations', Registration.objects.filter(event__in=events_qs, status='cancelled').count()),
        ('Waitlisted', WaitlistEntry.objects.filter(
            event__in=events_qs, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
        ).count()),
    ]
    return {
        'title': 'Event Summary Report',
        'subtitle': _subtitle(event, user),
        'summary': summary,
        'columns': columns,
        'currency_columns': {9, 10, 11, 12},
        'rows': rows,
    }


# --- 4. Vendor performance report (Module 4) -------------------------------

def build_vendor_performance_report(events_qs, event, user, request):
    # Scoped to vendor activity tied to events in `events_qs`: an Organizer
    # sees vendor performance on their own events only, Staff/Super Admin
    # see it across every event. A vendor with contracts/ratings on events
    # outside this scope simply won't show up here — that's intentional,
    # this report is "how did vendors perform on these events", not a
    # global vendor directory.
    ratings = VendorRating.objects.filter(event__in=events_qs)
    contracts = VendorContract.objects.filter(event__in=events_qs)
    vendor_ids = set(ratings.values_list('vendor_id', flat=True)) | set(contracts.values_list('vendor_id', flat=True))
    vendors = VendorProfile.objects.filter(pk__in=vendor_ids).order_by('company_name')

    columns = [
        'Vendor', 'Service Type', 'Avg Service Quality', 'Avg Delivery Time',
        'Performance Score', 'Ratings', 'Contracts', 'Contract Value', 'Paid to Vendor',
    ]
    rows = []
    total_contract_value = 0
    total_paid = 0
    for v in vendors:
        v_ratings = ratings.filter(vendor=v)
        v_contracts = contracts.filter(vendor=v)
        agg = v_ratings.aggregate(avg_quality=Avg('service_quality'), avg_delivery=Avg('delivery_time'))
        avg_quality, avg_delivery = agg['avg_quality'], agg['avg_delivery']
        score = round((avg_quality + avg_delivery) / 2, 2) if avg_quality is not None and avg_delivery is not None else None
        contract_value = v_contracts.aggregate(v=Sum('amount'))['v'] or 0
        paid = VendorPayment.objects.filter(contract__in=v_contracts, status='paid').aggregate(v=Sum('amount'))['v'] or 0
        total_contract_value += contract_value
        total_paid += paid
        rows.append([
            v.company_name,
            v.get_service_type_display(),
            round(avg_quality, 2) if avg_quality is not None else '—',
            round(avg_delivery, 2) if avg_delivery is not None else '—',
            score if score is not None else '—',
            v_ratings.count(),
            v_contracts.count(),
            contract_value,
            paid,
        ])

    summary = [
        ('Vendors Involved', vendors.count()),
        ('Total Contract Value', total_contract_value),
        ('Total Paid to Vendors', total_paid),
    ]
    return {
        'title': 'Vendor Performance Report',
        'subtitle': _subtitle(event, user),
        'summary': summary,
        'columns': columns,
        'currency_columns': {7, 8},
        'rows': rows,
    }


# --- 5. Staff performance report (Module 5) --------------------------------

def build_staff_performance_report(events_qs, event, user, request):
    shifts = ShiftAssignment.objects.filter(event__in=events_qs)
    staff_ids = set(shifts.values_list('staff_id', flat=True))
    staff_members = StaffProfile.objects.filter(pk__in=staff_ids).select_related('user', 'department').order_by('employee_id')

    columns = [
        'Staff', 'Employee ID', 'Department', 'Shifts', 'Completed Shifts',
        'Present', 'Absent', 'Late', 'Half Day', 'Attendance Rate',
    ]
    rows = []
    for s in staff_members:
        s_shifts = shifts.filter(staff=s)
        # Attendance scoped to shifts belonging to these events only, so an
        # Organizer's staff report can't pick up attendance recorded
        # against that person's shifts on someone else's event.
        records = AttendanceRecord.objects.filter(staff=s, shift__in=s_shifts)
        present = records.filter(status='present').count()
        absent = records.filter(status='absent').count()
        late = records.filter(status='late').count()
        half_day = records.filter(status='half_day').count()
        total_records = records.count()
        rate = round((present + late + half_day) / total_records * 100, 1) if total_records else None
        rows.append([
            _display_name(s.user),
            s.employee_id,
            s.department.name if s.department else '—',
            s_shifts.count(),
            s_shifts.filter(status='completed').count(),
            present,
            absent,
            late,
            half_day,
            f"{rate}%" if rate is not None else '—',
        ])

    summary = [
        ('Staff Involved', staff_members.count()),
        ('Total Shifts', shifts.count()),
        ('Completed Shifts', shifts.filter(status='completed').count()),
    ]
    return {
        'title': 'Staff Performance Report',
        'subtitle': _subtitle(event, user),
        'summary': summary,
        'columns': columns,
        'currency_columns': set(),
        'rows': rows,
    }


# --- 6. Resource utilization report (Module 3) -----------------------------

def _resolve_period(request):
    """Reads ?start=YYYY-MM-DD&end=YYYY-MM-DD, defaulting to the last 90 days."""
    end = timezone.now()
    start = end - timezone.timedelta(days=90)

    start_param = request.GET.get('start')
    end_param = request.GET.get('end')
    if start_param:
        parsed = parse_date(start_param)
        if parsed:
            start = timezone.make_aware(datetime.combine(parsed, time.min))
    if end_param:
        parsed = parse_date(end_param)
        if parsed:
            end = timezone.make_aware(datetime.combine(parsed, time.max))
    return start, end


def build_resource_utilization_report(events_qs, event, user, request):
    start, end = _resolve_period(request)
    period_hours = max((end - start).total_seconds() / 3600, 1)

    allocations = ResourceAllocation.objects.filter(
        status__in=['allocated', 'returned'],
        start_datetime__lt=end, end_datetime__gt=start,
    )
    if event is not None:
        allocations = allocations.filter(event=event)
    elif not (user.is_super_admin or user.is_staff_role):
        # Organizer scope: only allocations tied to one of their own
        # events. Allocations with no event at all are general/platform
        # bookings outside any single organizer's ownership, so they're
        # visible to Staff/Super Admin only.
        allocations = allocations.filter(event__in=events_qs)

    columns = ['Resource', 'Category', 'Total Quantity', 'Unit', 'Allocations', 'Unit-Hours Used', 'Pool Capacity (Unit-Hours)', 'Utilization %']
    rows = []
    for resource in Resource.objects.filter(is_active=True):
        r_allocs = allocations.filter(resource=resource)
        if not r_allocs.exists():
            continue  # a large idle inventory would otherwise bury the resources actually in use

        unit_hours_used = 0.0
        for alloc in r_allocs:
            overlap_start = max(alloc.start_datetime, start)
            overlap_end = min(alloc.end_datetime, end)
            hours = max((overlap_end - overlap_start).total_seconds() / 3600, 0)
            unit_hours_used += hours * alloc.quantity

        pool_capacity = resource.total_quantity * period_hours
        utilization = round((unit_hours_used / pool_capacity) * 100, 1) if pool_capacity else 0
        rows.append([
            resource.name,
            resource.get_category_display(),
            resource.total_quantity,
            resource.unit,
            r_allocs.count(),
            round(unit_hours_used, 1),
            round(pool_capacity, 1),
            utilization,
        ])

    rows.sort(key=lambda r: r[-1], reverse=True)

    summary = [
        ('Period', f"{timezone.localtime(start):%Y-%m-%d} to {timezone.localtime(end):%Y-%m-%d}"),
        ('Resources In Use', len(rows)),
        ('Total Allocations', allocations.count()),
    ]
    return {
        'title': 'Resource Utilization Report',
        'subtitle': _subtitle(event, user),
        'summary': summary,
        'columns': columns,
        'currency_columns': set(),
        'rows': rows,
        'period_start': start,
        'period_end': end,
    }
