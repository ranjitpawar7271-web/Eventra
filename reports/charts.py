"""
Data aggregation for the Analytics Dashboard's inline charts. Distinct from
data.py: report builders there produce exportable tables, this module
produces small, JSON-serializable {labels, data} shapes for Chart.js.

Everything returned here is a plain str/int/float so it can go straight
through `{{ charts|json_script:"..." }}` in the template without a custom
encoder.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from budget.models import EventBudget, Expense, RevenueEntry
from events.models import Registration
from payments.models import Payment
from resources.models import ResourceAllocation
from tickets.models import CheckInLog
from vendors.models import VendorRating


def _last_n_months(n=6):
    first_of_this_month = timezone.localdate().replace(day=1)
    months = []
    for i in range(n - 1, -1, -1):
        year, month = first_of_this_month.year, first_of_this_month.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append((year, month))
    return months


def _month_label(year, month):
    return timezone.datetime(year, month, 1).strftime('%b %Y')


def _monthly_counts(queryset, date_field):
    raw = (
        queryset.annotate(month=TruncMonth(date_field))
        .values('month')
        .annotate(total=Count('id'))
    )
    return {(row['month'].year, row['month'].month): row['total'] for row in raw if row['month']}


def _monthly_sums(queryset, date_field, sum_field):
    raw = (
        queryset.annotate(month=TruncMonth(date_field))
        .values('month')
        .annotate(total=Sum(sum_field))
    )
    return {(row['month'].year, row['month'].month): float(row['total'] or 0) for row in raw if row['month']}


def build_dashboard_charts(events_qs, user):
    months = _last_n_months(6)
    month_labels = [_month_label(y, m) for y, m in months]

    # --- Registration trends (Module 1: Registration) --------------------
    reg_map = _monthly_counts(
        Registration.objects.filter(event__in=events_qs, status='confirmed'), 'registered_at'
    )
    registration_trends = {'labels': month_labels, 'data': [reg_map.get(k, 0) for k in months]}

    # --- Attendance trends (Module 7: CheckInLog) -------------------------
    attendance_map = _monthly_counts(
        CheckInLog.objects.filter(event__in=events_qs, result=CheckInLog.RESULT_CHECKED_IN), 'scanned_at'
    )
    attendance_trends = {'labels': month_labels, 'data': [attendance_map.get(k, 0) for k in months]}

    # --- Revenue vs. expense trends (Module 6 manual entries + Phase 3
    # ticket-sale payments — same "derive live, don't duplicate" rule
    # EventBudget.total_revenue follows) ------------------------------
    revenue_map = _monthly_sums(RevenueEntry.objects.filter(budget__event__in=events_qs), 'date', 'amount')
    ticket_revenue_map = _monthly_sums(
        Payment.objects.filter(event__in=events_qs, status=Payment.STATUS_SUCCESSFUL), 'payment_date', 'amount'
    )
    expense_map = _monthly_sums(
        Expense.objects.filter(budget__event__in=events_qs, status__in=EventBudget.CONFIRMED_EXPENSE_STATUSES),
        'date', 'amount'
    )
    revenue_expense_trends = {
        'labels': month_labels,
        'revenue': [revenue_map.get(k, 0) + ticket_revenue_map.get(k, 0) for k in months],
        'expense': [expense_map.get(k, 0) for k in months],
    }

    # --- Event popularity (top 8 by confirmed registrations) --------------
    popular = list(
        events_qs.annotate(
            reg_count=Count('registrations', filter=Q(registrations__status='confirmed'))
        ).order_by('-reg_count')[:8]
    )
    event_popularity = {
        'labels': [e.title[:24] for e in popular],
        'data': [e.reg_count for e in popular],
    }

    # --- Vendor ratings (top 8 by performance score, scoped to these events) ---
    vendor_agg = list(
        VendorRating.objects.filter(event__in=events_qs)
        .values('vendor__company_name')
        .annotate(avg_quality=Avg('service_quality'), avg_delivery=Avg('delivery_time'), count=Count('id'))
    )
    vendor_agg.sort(
        key=lambda r: ((r['avg_quality'] or 0) + (r['avg_delivery'] or 0)) / 2,
        reverse=True,
    )
    vendor_agg = vendor_agg[:8]
    vendor_ratings = {
        'labels': [r['vendor__company_name'][:20] for r in vendor_agg],
        'data': [round(((r['avg_quality'] or 0) + (r['avg_delivery'] or 0)) / 2, 2) for r in vendor_agg],
    }

    # --- Resource usage (top 8 by allocated quantity, last 90 days) -------
    period_end = timezone.now()
    period_start = period_end - timedelta(days=90)
    alloc_qs = ResourceAllocation.objects.filter(
        status__in=['allocated', 'returned'],
        start_datetime__lt=period_end, end_datetime__gt=period_start,
    )
    if not (user.is_super_admin or user.is_staff_role):
        alloc_qs = alloc_qs.filter(event__in=events_qs)

    resource_agg = list(
        alloc_qs.values('resource__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:8]
    )
    resource_usage = {
        'labels': [r['resource__name'][:20] for r in resource_agg],
        'data': [r['total_qty'] or 0 for r in resource_agg],
    }

    return {
        'registration_trends': registration_trends,
        'attendance_trends': attendance_trends,
        'revenue_expense_trends': revenue_expense_trends,
        'event_popularity': event_popularity,
        'vendor_ratings': vendor_ratings,
        'resource_usage': resource_usage,
    }
