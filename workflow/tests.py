"""
Real, executable coverage for the workflow app (Module 9), matching the
project's "every module gets real tests" convention (see tickets/tests.py).

Run with:
    python manage.py test workflow
"""
import uuid
from datetime import timedelta
from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from budget.models import EventBudget, Expense
from categories.models import Category
from events.models import Event, Registration
from staff.models import Department, ShiftAssignment, StaffProfile
from users.models import User
from vendors.models import VendorContract, VendorProfile

from .models import ApprovalStep, Notification, WorkflowSettings


def _make_user(username, role=User.PARTICIPANT, **kwargs):
    return User.objects.create_user(
        username=username, password='pass1234', role=role,
        email=f'{username}@example.com', **kwargs
    )


def _make_event(organizer, **kwargs):
    category = Category.objects.create(name=f'Cat-{uuid.uuid4().hex[:10]}')
    defaults = dict(
        title=f"Event by {organizer.username}",
        description='desc',
        organizer=organizer,
        category=category,
        location='Test Hall',
        start_date=timezone.now() + timedelta(days=1),
        end_date=timezone.now() + timedelta(days=1, hours=2),
        capacity=50,
        status='draft',
    )
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


class ApprovalGateTests(TestCase):
    """Event Draft -> Published gate, toggled by WorkflowSettings."""

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.admin = _make_user('admin1', role=User.SUPER_ADMIN)

    def test_publish_allowed_when_approval_not_required(self):
        # Default WorkflowSettings has require_event_approval=False.
        event = _make_event(self.organizer)
        event.status = 'published'
        event.save(update_fields=['status'])
        event.refresh_from_db()
        self.assertEqual(event.status, 'published')
        self.assertFalse(ApprovalStep.objects.exists())

    def test_publish_held_back_when_approval_required(self):
        settings_row = WorkflowSettings.get_solo()
        settings_row.require_event_approval = True
        settings_row.save()

        event = _make_event(self.organizer)
        event.status = 'published'
        event.save(update_fields=['status'])
        event.refresh_from_db()

        self.assertEqual(event.status, 'draft')
        step = ApprovalStep.objects.get(
            content_type=ContentType.objects.get_for_model(Event), object_id=event.pk,
        )
        self.assertEqual(step.status, ApprovalStep.STATUS_PENDING)
        self.assertEqual(step.stage, ApprovalStep.STAGE_PUBLISHED)

        # Organizer was notified that it's pending, and admins were notified
        # there's something to review.
        self.assertTrue(
            Notification.objects.filter(user=self.organizer, notification_type=Notification.TYPE_APPROVAL).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.admin, notification_type=Notification.TYPE_APPROVAL).exists()
        )

    def test_approving_step_publishes_event(self):
        settings_row = WorkflowSettings.get_solo()
        settings_row.require_event_approval = True
        settings_row.save()

        event = _make_event(self.organizer)
        event.status = 'published'
        event.save(update_fields=['status'])
        event.refresh_from_db()
        self.assertEqual(event.status, 'draft')

        step = ApprovalStep.objects.get(object_id=event.pk)
        step.approve(self.admin, comment='Looks good')
        event.refresh_from_db()

        self.assertEqual(event.status, 'published')
        self.assertEqual(step.status, ApprovalStep.STATUS_APPROVED)
        self.assertEqual(step.decided_by, self.admin)
        self.assertTrue(
            Notification.objects.filter(
                user=self.organizer, message__icontains='approved and is now live'
            ).exists()
        )

    def test_rejecting_step_keeps_event_draft(self):
        settings_row = WorkflowSettings.get_solo()
        settings_row.require_event_approval = True
        settings_row.save()

        event = _make_event(self.organizer)
        event.status = 'published'
        event.save(update_fields=['status'])

        step = ApprovalStep.objects.get(object_id=event.pk)
        step.reject(self.admin, comment='Missing venue details')
        event.refresh_from_db()

        self.assertEqual(event.status, 'draft')
        self.assertEqual(step.status, ApprovalStep.STATUS_REJECTED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.organizer, message__icontains='Missing venue details'
            ).exists()
        )

    def test_second_save_does_not_create_duplicate_approval_step(self):
        settings_row = WorkflowSettings.get_solo()
        settings_row.require_event_approval = True
        settings_row.save()

        event = _make_event(self.organizer)
        event.status = 'published'
        event.save(update_fields=['status'])
        # Saving again with status still (bounced back to) 'draft' shouldn't
        # create a second pending step for the same publish request.
        event.title = event.title + ' (edited)'
        event.save(update_fields=['title'])

        self.assertEqual(
            ApprovalStep.objects.filter(object_id=event.pk, status=ApprovalStep.STATUS_PENDING).count(), 1
        )


class ApprovalViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.organizer = _make_user('organizer2', role=User.ORGANIZER)
        self.admin = _make_user('admin2', role=User.SUPER_ADMIN)
        self.participant = _make_user('participant2', role=User.PARTICIPANT)

        settings_row = WorkflowSettings.get_solo()
        settings_row.require_event_approval = True
        settings_row.save()

        self.event = _make_event(self.organizer)
        self.event.status = 'published'
        self.event.save(update_fields=['status'])
        self.step = ApprovalStep.objects.get(object_id=self.event.pk)

    def test_non_admin_cannot_view_approval_queue(self):
        self.client.login(username='participant2', password='pass1234')
        response = self.client.get(reverse('workflow:approval_list'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_admin_can_view_approval_queue(self):
        self.client.login(username='admin2', password='pass1234')
        response = self.client.get(reverse('workflow:approval_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_admin_can_approve_via_view(self):
        self.client.login(username='admin2', password='pass1234')
        response = self.client.post(
            reverse('workflow:approval_decide', args=[self.step.pk, 'approve']), {'comment': 'ok'}
        )
        self.assertRedirects(response, reverse('workflow:approval_list'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'published')

    def test_non_admin_cannot_approve_via_view(self):
        self.client.login(username='organizer2', password='pass1234')
        response = self.client.post(
            reverse('workflow:approval_decide', args=[self.step.pk, 'approve']), {'comment': ''}
        )
        self.assertRedirects(response, reverse('dashboard:dashboard'))
        self.step.refresh_from_db()
        self.assertEqual(self.step.status, ApprovalStep.STATUS_PENDING)


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user = _make_user('notifyme')

    def test_notify_creates_notification_and_sends_email(self):
        mail.outbox = []
        notification = Notification.notify(self.user, "Hello there", notification_type=Notification.TYPE_SYSTEM)
        self.assertIsNotNone(notification)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_dedupe_key_prevents_duplicate(self):
        first = Notification.notify(self.user, "First", dedupe_key='rule-1')
        second = Notification.notify(self.user, "Second (should be skipped)", dedupe_key='rule-1')
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_blank_dedupe_key_never_collides(self):
        Notification.notify(self.user, "Ad-hoc one")
        Notification.notify(self.user, "Ad-hoc two")
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 2)


class NotificationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _make_user('viewer1')
        self.other = _make_user('viewer2')
        self.n1 = Notification.objects.create(user=self.user, message='For me', link='/events/')
        self.n2 = Notification.objects.create(user=self.other, message='Not for me')

    def test_list_only_shows_own_notifications(self):
        self.client.login(username='viewer1', password='pass1234')
        response = self.client.get(reverse('workflow:notification_list'))
        self.assertContains(response, 'For me')
        self.assertNotContains(response, 'Not for me')

    def test_read_marks_as_read_and_redirects_to_link(self):
        self.client.login(username='viewer1', password='pass1234')
        response = self.client.get(reverse('workflow:notification_read', args=[self.n1.pk]))
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertRedirects(response, '/events/')

    def test_cannot_read_someone_elses_notification(self):
        self.client.login(username='viewer1', password='pass1234')
        response = self.client.get(reverse('workflow:notification_read', args=[self.n2.pk]))
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read(self):
        Notification.objects.create(user=self.user, message='Second unread')
        self.client.login(username='viewer1', password='pass1234')
        self.client.post(reverse('workflow:notifications_mark_all_read'))
        self.assertFalse(Notification.objects.filter(user=self.user, is_read=False).exists())


class CalendarViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.organizer = _make_user('calorg', role=User.ORGANIZER)
        self.event = _make_event(self.organizer, status='published')

    def test_calendar_requires_login(self):
        response = self.client.get(reverse('workflow:calendar'))
        self.assertNotEqual(response.status_code, 200)

    def test_month_view_shows_published_event(self):
        self.client.login(username='calorg', password='pass1234')
        response = self.client.get(reverse('workflow:calendar'), {'view': 'month'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_day_view_for_event_date(self):
        self.client.login(username='calorg', password='pass1234')
        response = self.client.get(
            reverse('workflow:calendar'),
            {'view': 'day', 'date': self.event.start_date.date().isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)


class StaffAssignmentSignalTests(TestCase):
    def test_shift_creation_notifies_staff(self):
        dept = Department.objects.create(name='Ops')
        staff_user = _make_user('shiftstaff', role=User.STAFF)
        profile = StaffProfile.objects.create(user=staff_user, employee_id='EMP-900', department=dept)

        ShiftAssignment.objects.create(
            staff=profile, title='Gate Duty',
            start_datetime=timezone.now() + timedelta(hours=2),
            end_datetime=timezone.now() + timedelta(hours=5),
            status='assigned',
        )

        self.assertTrue(
            Notification.objects.filter(user=staff_user, notification_type=Notification.TYPE_STAFF).exists()
        )


class VendorContractSignalTests(TestCase):
    def test_contract_sent_notifies_vendor(self):
        vendor_user = _make_user('vendoruser', role=User.VENDOR)
        vendor = VendorProfile.objects.create(user=vendor_user, company_name='Acme Catering')

        VendorContract.objects.create(vendor=vendor, title='Catering Agreement', status='sent')

        self.assertTrue(
            Notification.objects.filter(user=vendor_user, notification_type=Notification.TYPE_VENDOR).exists()
        )


class SendRemindersCommandTests(TestCase):
    def setUp(self):
        self.organizer = _make_user('reminderorg', role=User.ORGANIZER)
        self.participant = _make_user('reminderpart', role=User.PARTICIPANT)

    def test_event_tomorrow_reminder_sent_to_registrant_and_organizer(self):
        event = _make_event(
            self.organizer, status='published',
            start_date=timezone.now() + timedelta(hours=24),
            end_date=timezone.now() + timedelta(hours=26),
        )
        Registration.objects.create(event=event, user=self.participant, status='confirmed')

        out = StringIO()
        call_command('send_reminders', stdout=out)

        self.assertTrue(
            Notification.objects.filter(user=self.participant, notification_type=Notification.TYPE_REMINDER).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.organizer, notification_type=Notification.TYPE_REMINDER).exists()
        )

    def test_running_twice_does_not_duplicate(self):
        event = _make_event(
            self.organizer, status='published',
            start_date=timezone.now() + timedelta(hours=24),
            end_date=timezone.now() + timedelta(hours=26),
        )
        Registration.objects.create(event=event, user=self.participant, status='confirmed')

        call_command('send_reminders', stdout=StringIO())
        call_command('send_reminders', stdout=StringIO())

        self.assertEqual(
            Notification.objects.filter(user=self.participant, notification_type=Notification.TYPE_REMINDER).count(),
            1,
        )

    def test_pending_expense_reminder(self):
        event = _make_event(self.organizer, status='published')
        budget = EventBudget.objects.create(event=event, estimated_budget=10000)
        expense = Expense.objects.create(
            budget=budget, category='venue', description='Hall rent', amount=2000,
            date=timezone.now().date(), status='pending',
        )
        # Backdate creation past the 2-day staleness window.
        Expense.objects.filter(pk=expense.pk).update(created_at=timezone.now() - timedelta(days=3))

        call_command('send_reminders', stdout=StringIO())

        self.assertTrue(
            Notification.objects.filter(user=self.organizer, notification_type=Notification.TYPE_PAYMENT).exists()
        )
