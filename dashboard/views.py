from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import render
from django.utils import timezone

from categories.models import Category
from budget.models import EventBudget, Expense, RevenueEntry
from certificates.models import Certificate
from events.models import Event, Registration, WaitlistEntry
from payments.models import Payment
from sponsors.models import EventSponsorship
from tasks.models import Task
from tickets.models import Ticket
from users.models import User
from vendors.models import VendorPayment
from wishlist.models import FavoriteEvent
from workflow.models import ApprovalStep, Notification


@login_required
def dashboard_view(request):
    user = request.user

    my_events = Event.objects.filter(organizer=user)
    my_registrations = Registration.objects.filter(user=user, status='confirmed')

    upcoming_events = Event.objects.filter(
        status='published', start_date__gte=timezone.now()
    ).select_related('category').order_by('start_date')[:5]

    recent_registrations = (
        Registration.objects.filter(event__organizer=user)
        .select_related('event', 'user')
        .order_by('-registered_at')[:5]
    )

    recent_events = my_events.select_related('category').order_by('-created_at')[:5]

    total_participants = Registration.objects.filter(
        event__organizer=user, status='confirmed'
    ).count()

    my_upcoming_count = my_events.filter(start_date__gte=timezone.now()).count()
    my_completed_count = my_events.filter(status='completed').count()
    my_cancelled_count = my_events.filter(status='cancelled').count()

    # --- Workflow snapshot (Module 9) -------------------------------
    my_pending_approvals = ApprovalStep.objects.filter(
        requested_by=user, status=ApprovalStep.STATUS_PENDING
    ).count()
    my_unread_notifications = Notification.objects.filter(user=user, is_read=False).count()

    # --- Budget snapshot (Module 6) --------------------------------
    # Organizers see the totals across their own events' budgets only;
    # Staff/Super Admin get the system-wide numbers below instead.
    my_budgets = EventBudget.objects.filter(event__organizer=user)
    my_estimated_budget = my_budgets.aggregate(v=models.Sum('estimated_budget'))['v'] or 0
    my_total_expenses = sum(b.total_expenses for b in my_budgets)
    my_total_revenue = sum(b.total_revenue for b in my_budgets)

    # --- Registration / Attendance / Ticketing snapshot (Phase 13) -----
    # The report_hub has these broken out per-event; this is the
    # at-a-glance version across all of an organizer's events, matching
    # the spec's "Organizer dashboard should show" stat groups.
    my_reg_confirmed = total_participants
    my_reg_cancelled = Registration.objects.filter(event__organizer=user, status='cancelled').count()
    my_reg_waitlisted = WaitlistEntry.objects.filter(
        event__organizer=user, status__in=[WaitlistEntry.STATUS_WAITING, WaitlistEntry.STATUS_NOTIFIED]
    ).count()

    my_tickets_qs = Ticket.objects.filter(registration__event__organizer=user)
    my_tickets_generated = my_tickets_qs.count()
    my_tickets_used = my_tickets_qs.filter(status=Ticket.STATUS_CHECKED_IN).count()
    my_tickets_unused = my_tickets_qs.filter(status=Ticket.STATUS_ISSUED).count()
    my_attendance_rate = round((my_tickets_used / my_reg_confirmed) * 100, 1) if my_reg_confirmed else 0

    my_payments_qs = Payment.objects.filter(event__organizer=user)
    my_payments_successful = my_payments_qs.filter(status=Payment.STATUS_SUCCESSFUL).count()
    my_payments_pending = my_payments_qs.filter(status=Payment.STATUS_PENDING).count()
    my_payments_failed = my_payments_qs.filter(status=Payment.STATUS_FAILED).count()
    my_payments_refunded = my_payments_qs.filter(status=Payment.STATUS_REFUNDED).count()

    context = {
        'total_events': my_events.count(),
        'total_categories': Category.objects.count(),
        'total_participants': total_participants,
        'my_registrations_count': my_registrations.count(),
        'my_upcoming_count': my_upcoming_count,
        'my_completed_count': my_completed_count,
        'my_cancelled_count': my_cancelled_count,
        'upcoming_events': upcoming_events,
        'recent_registrations': recent_registrations,
        'recent_events': recent_events,
        'user_role': user.role,
        'my_estimated_budget': my_estimated_budget,
        'my_total_expenses': my_total_expenses,
        'my_total_revenue': my_total_revenue,
        'my_profit_or_loss': my_total_revenue - my_total_expenses,
        'has_budgets': my_budgets.exists(),
        'my_pending_approvals': my_pending_approvals,
        'my_unread_notifications': my_unread_notifications,
        'my_reg_confirmed': my_reg_confirmed,
        'my_reg_cancelled': my_reg_cancelled,
        'my_reg_waitlisted': my_reg_waitlisted,
        'my_tickets_generated': my_tickets_generated,
        'my_tickets_used': my_tickets_used,
        'my_tickets_unused': my_tickets_unused,
        'my_attendance_rate': my_attendance_rate,
        'my_payments_successful': my_payments_successful,
        'my_payments_pending': my_payments_pending,
        'my_payments_failed': my_payments_failed,
        'my_payments_refunded': my_payments_refunded,
        'has_registration_activity': my_reg_confirmed or my_reg_cancelled or my_reg_waitlisted or my_tickets_generated,
    }

    # --- Super Admin: system-wide overview -----------------------------
    # Everything here is computed from data that already exists (Event,
    # User, Registration, and now Budget/Expense/RevenueEntry). The
    # resource-utilization and approval-queue widgets from the full spec
    # still depend on modules that come later, so they aren't faked here
    # — they'll light up once those land.
    if user.is_super_admin:
        now = timezone.now()
        all_events = Event.objects.all()
        context.update({
            'is_admin_view': True,
            'sys_total_events': all_events.count(),
            'sys_active_events': all_events.filter(
                status='published', start_date__lte=now, end_date__gte=now
            ).count(),
            'sys_upcoming_events': all_events.filter(
                status='published', start_date__gt=now
            ).count(),
            'sys_completed_events': all_events.filter(status='completed').count(),
            'sys_cancelled_events': all_events.filter(status='cancelled').count(),
            'sys_total_users': User.objects.count(),
            'sys_total_participants': User.objects.filter(role=User.PARTICIPANT).count(),
            'sys_total_organizers': User.objects.filter(role=User.ORGANIZER).count(),
            'sys_total_staff': User.objects.filter(role=User.STAFF).count(),
            'sys_total_vendors': User.objects.filter(role=User.VENDOR).count(),
            'sys_total_volunteers': User.objects.filter(role=User.VOLUNTEER).count(),
            'sys_total_registrations': Registration.objects.filter(status='confirmed').count(),
            'sys_manual_revenue': RevenueEntry.objects.aggregate(v=models.Sum('amount'))['v'] or 0,
            'sys_sponsorship_revenue': EventSponsorship.objects.filter(
                status__in=EventSponsorship.CONFIRMED_STATUSES
            ).aggregate(v=models.Sum('amount'))['v'] or 0,
            'sys_direct_expenses': Expense.objects.filter(
                status__in=EventBudget.CONFIRMED_EXPENSE_STATUSES
            ).aggregate(v=models.Sum('amount'))['v'] or 0,
            'sys_vendor_payments': VendorPayment.objects.filter(status='paid').aggregate(v=models.Sum('amount'))['v'] or 0,
            'sys_pending_approvals': ApprovalStep.objects.filter(status=ApprovalStep.STATUS_PENDING).count(),
        })
        context['sys_total_revenue'] = context['sys_manual_revenue'] + context['sys_sponsorship_revenue']
        context['sys_total_expenses'] = context['sys_direct_expenses'] + context['sys_vendor_payments']
        context['sys_net_profit'] = context['sys_total_revenue'] - context['sys_total_expenses']

    return render(request, 'dashboard/dashboard.html', context)


ACTIVITY_FEED_LIMIT = 50


@login_required
def activity_feed(request):
    """'Activity Feed' (Module 10): a read-only aggregation over existing
    timestamped records, not a new event-sourcing/log table. Wiring a
    signal-based ActivityLog into every app that could produce an entry
    would touch a dozen files for something this view already gets by
    just querying each app's own timestamp field directly — the data to
    show already exists, so this only needs to read and merge it.
    """
    user = request.user
    entries = []

    for reg in Registration.objects.filter(user=user).select_related('event')[:ACTIVITY_FEED_LIMIT]:
        entries.append({
            'icon': 'bi-ticket-perforated', 'timestamp': reg.registered_at,
            'text': f"You registered for \"{reg.event.title}\"",
            'url': reg.event.get_absolute_url(),
        })

    for fav in FavoriteEvent.objects.filter(user=user).select_related('event')[:ACTIVITY_FEED_LIMIT]:
        entries.append({
            'icon': 'bi-heart', 'timestamp': fav.created_at,
            'text': f"You added \"{fav.event.title}\" to your wishlist",
            'url': fav.event.get_absolute_url(),
        })

    for task in Task.objects.filter(assigned_to=user).select_related('event')[:ACTIVITY_FEED_LIMIT]:
        entries.append({
            'icon': 'bi-kanban', 'timestamp': task.created_at,
            'text': f"You were assigned \"{task.title}\" on \"{task.event.title}\"",
            'url': task.event.get_absolute_url(),
        })

    for cert in Certificate.objects.filter(ticket__registration__user=user).select_related(
        'ticket__registration__event'
    )[:ACTIVITY_FEED_LIMIT]:
        entries.append({
            'icon': 'bi-award', 'timestamp': cert.issued_at,
            'text': f"You earned a {cert.get_cert_type_display().lower()} for \"{cert.event.title}\"",
            'url': cert.get_absolute_url(),
        })

    if user.can_manage_events:
        for event in Event.objects.filter(organizer=user)[:ACTIVITY_FEED_LIMIT]:
            entries.append({
                'icon': 'bi-calendar-plus', 'timestamp': event.created_at,
                'text': f"You created \"{event.title}\"",
                'url': event.get_absolute_url(),
            })

    entries.sort(key=lambda e: e['timestamp'], reverse=True)
    entries = entries[:ACTIVITY_FEED_LIMIT]

    return render(request, 'dashboard/activity_feed.html', {'entries': entries})

