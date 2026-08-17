from django.http import Http404
from django.shortcuts import get_object_or_404, render

from events.models import Event
from users.models import User
from users.permissions import role_required
from . import charts as report_charts
from . import data as report_data
from .export import csv_response, pdf_response, xlsx_response

# Per spec: Organizer reports are scoped to their own events; Super Admin
# and Staff get system-wide reports. Reuses the same role set already
# established for scanning/managing tickets in Module 7.
REPORT_ROLES = (User.SUPER_ADMIN, User.ORGANIZER, User.STAFF)

REPORT_TYPES = {
    'attendance': {'label': 'Attendance Report', 'builder': report_data.build_attendance_report},
    'financial': {'label': 'Revenue / Expense / Profit-Loss Report', 'builder': report_data.build_financial_report},
    'event_summary': {'label': 'Event Summary Report', 'builder': report_data.build_event_summary_report},
    'vendor_performance': {'label': 'Vendor Performance Report', 'builder': report_data.build_vendor_performance_report},
    'staff_performance': {'label': 'Staff Performance Report', 'builder': report_data.build_staff_performance_report},
    'resource_utilization': {'label': 'Resource Utilization Report', 'builder': report_data.build_resource_utilization_report},
}


def _scoped_events(user):
    if user.is_super_admin or user.is_staff_role:
        return Event.objects.all()
    return Event.objects.filter(organizer=user)


@role_required(*REPORT_ROLES)
def report_hub(request):
    events_qs = _scoped_events(request.user).select_related('category').order_by('-start_date')
    context = {
        'report_types': [{'key': key, 'label': meta['label']} for key, meta in REPORT_TYPES.items()],
        'events': events_qs[:200],
        'is_system_wide': request.user.is_super_admin or request.user.is_staff_role,
    }
    return render(request, 'reports/report_hub.html', context)


@role_required(*REPORT_ROLES)
def report_view(request, report_type, slug=None):
    if report_type not in REPORT_TYPES:
        raise Http404("Unknown report type.")

    events_qs = _scoped_events(request.user)
    event = None
    if slug:
        # get_object_or_404 against the *scoped* queryset means an
        # Organizer requesting a slug they don't own gets a plain 404,
        # not a peek at another organizer's numbers.
        event = get_object_or_404(events_qs, slug=slug)
        report_events_qs = Event.objects.filter(pk=event.pk)
    else:
        report_events_qs = events_qs

    builder = REPORT_TYPES[report_type]['builder']
    report = builder(report_events_qs, event, request.user, request)

    export_format = request.GET.get('format', 'html')
    if export_format == 'csv':
        return csv_response(report)
    if export_format == 'xlsx':
        return xlsx_response(report)
    if export_format == 'pdf':
        return pdf_response(report)

    return render(request, 'reports/report_detail.html', {
        'report': report,
        'report_type': report_type,
        'report_label': REPORT_TYPES[report_type]['label'],
        'event': event,
        'events': events_qs.order_by('-start_date')[:200],
    })


@role_required(*REPORT_ROLES)
def analytics_dashboard(request):
    events_qs = _scoped_events(request.user)
    charts = report_charts.build_dashboard_charts(events_qs, request.user)
    return render(request, 'reports/analytics_dashboard.html', {
        'charts': charts,
        'is_system_wide': request.user.is_super_admin or request.user.is_staff_role,
    })
