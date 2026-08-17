"""
Scheduled reminders: registration closing soon, event tomorrow, payment
pending, staff assignment, vendor reminder — the exact list from the
Module 9 spec.

This project doesn't run a background scheduler (no Celery/cron worker
in this environment), so nothing calls this automatically. In
production, wire it up as either:

    # crontab, every 30 minutes
    */30 * * * * cd /path/to/project && python manage.py send_reminders

    # or a Celery beat task calling the same command:
    from django.core.management import call_command
    call_command('send_reminders')

Every notification created here sets a `dedupe_key`, so running this
command repeatedly (every 30 minutes, forever) never sends the same
reminder twice — Notification.notify() no-ops on a key it's already seen.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from budget.models import Expense
from events.models import Event, Registration
from staff.models import ShiftAssignment
from vendors.models import VendorContract, VendorPayment
from workflow.models import Notification


class Command(BaseCommand):
    help = "Sends the scheduled Module 9 reminders (registration closing, event tomorrow, payment pending, staff assignment, vendor reminder)."

    def handle(self, *args, **options):
        now = timezone.now()
        counts = {
            'registration_closing': self._registration_closing_soon(now),
            'event_tomorrow': self._event_tomorrow(now),
            'payment_pending': self._payment_pending(now),
            'staff_shift_reminder': self._staff_shift_reminder(now),
            'vendor_reminder': self._vendor_reminder(now),
            'capacity_warning': self._capacity_warning(now),
            'budget_warning': self._budget_warning(now),
            'task_deadline': self._task_deadline(now),
        }
        total = sum(counts.values())
        for rule, count in counts.items():
            self.stdout.write(f"  {rule}: {count} notification(s)")
        self.stdout.write(self.style.SUCCESS(f"send_reminders done — {total} notification(s) sent."))

    # --- Registration closing soon (event starts within 24h, seats open) ---
    def _registration_closing_soon(self, now):
        sent = 0
        window_end = now + timedelta(hours=24)
        events = Event.objects.filter(
            status='published', start_date__gte=now, start_date__lte=window_end,
        )
        for event in events:
            if event.is_full or not event.organizer:
                continue
            notification = Notification.notify(
                event.organizer,
                f"Registration for '{event.title}' closes soon — {event.seats_left} seat(s) left.",
                link=event.get_absolute_url(),
                notification_type=Notification.TYPE_REMINDER,
                dedupe_key=f'reg-closing-{event.pk}',
            )
            sent += 1 if notification else 0
        return sent

    # --- Event tomorrow (23-25h out), notify registrants + organizer ------
    def _event_tomorrow(self, now):
        sent = 0
        window_start = now + timedelta(hours=23)
        window_end = now + timedelta(hours=25)
        events = Event.objects.filter(
            status='published', start_date__gte=window_start, start_date__lte=window_end,
        )
        for event in events:
            when = event.start_date.strftime('%H:%M')
            if event.organizer:
                notification = Notification.notify(
                    event.organizer,
                    f"'{event.title}' is happening tomorrow at {when}.",
                    link=event.get_absolute_url(),
                    notification_type=Notification.TYPE_REMINDER,
                    dedupe_key=f'event-tomorrow-organizer-{event.pk}',
                )
                sent += 1 if notification else 0

            registrants = Registration.objects.filter(event=event, status='confirmed').select_related('user')
            for registration in registrants:
                notification = Notification.notify(
                    registration.user,
                    f"Reminder: '{event.title}' is tomorrow at {when}.",
                    link=event.get_absolute_url(),
                    notification_type=Notification.TYPE_REMINDER,
                    dedupe_key=f'event-tomorrow-{event.pk}-{registration.user_id}',
                )
                sent += 1 if notification else 0
        return sent

    # --- Payment pending (Module 6 expenses + vendor payments) -----------
    def _payment_pending(self, now):
        sent = 0
        stale_cutoff = now - timedelta(days=2)

        expenses = Expense.objects.filter(
            status='pending', created_at__lte=stale_cutoff
        ).select_related('budget__event__organizer')
        for expense in expenses:
            organizer = expense.budget.event.organizer
            if not organizer:
                continue
            notification = Notification.notify(
                organizer,
                f"Expense '{expense.description}' (₹{expense.amount}) on '{expense.budget.event.title}' is still pending approval.",
                link=expense.budget.get_absolute_url(),
                notification_type=Notification.TYPE_PAYMENT,
                dedupe_key=f'expense-pending-{expense.pk}',
            )
            sent += 1 if notification else 0

        vendor_payments = VendorPayment.objects.filter(
            status='pending', payment_date__lte=(now + timedelta(days=2)).date()
        ).select_related('vendor__user')
        for payment in vendor_payments:
            notification = Notification.notify(
                payment.vendor.user,
                f"A pending payment of ₹{payment.amount} to you is due {payment.payment_date}.",
                link=payment.vendor.get_absolute_url(),
                notification_type=Notification.TYPE_PAYMENT,
                dedupe_key=f'vendor-payment-pending-{payment.pk}',
            )
            sent += 1 if notification else 0
        return sent

    # --- Staff assignment reminder (shift starting within 24h) -----------
    def _staff_shift_reminder(self, now):
        sent = 0
        window_end = now + timedelta(hours=24)
        shifts = ShiftAssignment.objects.filter(
            status='assigned', start_datetime__gte=now, start_datetime__lte=window_end,
        ).select_related('staff__user')
        for shift in shifts:
            when = shift.start_datetime.strftime('%b %d, %H:%M')
            notification = Notification.notify(
                shift.staff.user,
                f"Upcoming shift: '{shift.title}' starts {when}.",
                link=reverse('staff:staff_detail', kwargs={'pk': shift.staff.pk}),
                notification_type=Notification.TYPE_STAFF,
                dedupe_key=f'shift-reminder-{shift.pk}',
            )
            sent += 1 if notification else 0
        return sent

    # --- Vendor reminder (contract sent but unsigned after 2 days) -------
    def _vendor_reminder(self, now):
        sent = 0
        stale_cutoff = now - timedelta(days=2)
        contracts = VendorContract.objects.filter(
            status='sent', created_at__lte=stale_cutoff
        ).select_related('vendor__user')
        for contract in contracts:
            notification = Notification.notify(
                contract.vendor.user,
                f"Contract '{contract.title}' is still awaiting your signature.",
                link=contract.vendor.get_absolute_url(),
                notification_type=Notification.TYPE_VENDOR,
                dedupe_key=f'contract-reminder-{contract.pk}',
            )
            sent += 1 if notification else 0
        return sent

    # --- Event capacity warning (event nearing full, still upcoming) -----
    def _capacity_warning(self, now):
        sent = 0
        events = Event.objects.filter(status='published', start_date__gte=now).select_related('organizer')
        for event in events:
            if not event.organizer or event.capacity <= 0:
                continue
            fill_ratio = event.seats_taken / event.capacity
            if fill_ratio < 0.9 or event.is_full:
                continue  # full already has its own "Event Full" UI state; this is the early-warning
            notification = Notification.notify(
                event.organizer,
                f"'{event.title}' is {round(fill_ratio * 100)}% full — {event.seats_left} seat(s) left.",
                link=event.get_absolute_url(),
                notification_type=Notification.TYPE_CAPACITY,
                priority=Notification.PRIORITY_HIGH,
                related_event=event,
                dedupe_key=f'capacity-warning-{event.pk}',
            )
            sent += 1 if notification else 0
        return sent

    # --- Budget warning (expenses approaching/over the estimated budget) -
    def _budget_warning(self, now):
        from budget.models import EventBudget

        sent = 0
        budgets = EventBudget.objects.select_related('event__organizer').filter(event__status__in=['published', 'draft'])
        for budget in budgets:
            if not budget.event.organizer or not budget.estimated_budget:
                continue
            ratio = budget.total_expenses / budget.estimated_budget
            if ratio < 0.9:
                continue
            over = ratio >= 1
            message = (
                f"Budget alert: '{budget.event.title}' has spent ₹{budget.total_expenses} of its "
                f"₹{budget.estimated_budget} budget ({round(ratio * 100)}%)."
            )
            notification = Notification.notify(
                budget.event.organizer,
                message,
                link=budget.get_absolute_url(),
                notification_type=Notification.TYPE_BUDGET,
                priority=Notification.PRIORITY_URGENT if over else Notification.PRIORITY_HIGH,
                related_event=budget.event,
                dedupe_key=f'budget-warning-{budget.pk}-{"over" if over else "near"}',
            )
            sent += 1 if notification else 0
        return sent

    # --- Task deadline (checklist item due within 24h, not yet done) -----
    def _task_deadline(self, now):
        from tasks.models import Task

        sent = 0
        tomorrow = (now + timedelta(hours=24)).date()
        tasks = Task.objects.filter(
            due_date__gte=now.date(), due_date__lte=tomorrow
        ).exclude(status='done').select_related('event', 'assigned_to')
        for task in tasks:
            assignee = task.assigned_to or task.event.organizer
            if not assignee:
                continue
            notification = Notification.notify(
                assignee,
                f"Task due soon: '{task.title}' for '{task.event.title}' is due {task.due_date}.",
                link=reverse('tasks:task_detail', kwargs={'pk': task.pk}),
                notification_type=Notification.TYPE_TASK,
                priority=Notification.PRIORITY_HIGH,
                related_event=task.event,
                dedupe_key=f'task-deadline-{task.pk}',
            )
            sent += 1 if notification else 0
        return sent
