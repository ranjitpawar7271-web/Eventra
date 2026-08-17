"""
Real, executable coverage for the reports app (Module 8).

Previously this file was Django's empty test-runner boilerplate — 0 real
tests. Reports has no models of its own (everything is computed live off
Events/Budget/Tickets/Vendors/Staff/Resources), so what actually needs
covering is: role-based scoping, cross-organizer isolation, and that each
export format produces a well-formed file for every report type.

Run with:
    python manage.py test reports

XLSX/PDF tests are skipped automatically if `openpyxl` / `reportlab`
aren't installed (see skipUnless guards), same policy as tickets/tests.py.
"""
import importlib.util
import unittest
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from events.models import Event, Registration
from tickets.models import Ticket

User = get_user_model()

HAS_OPENPYXL = importlib.util.find_spec('openpyxl') is not None
HAS_REPORTLAB = importlib.util.find_spec('reportlab') is not None

REPORT_TYPES = [
    'attendance', 'financial', 'event_summary',
    'vendor_performance', 'staff_performance', 'resource_utilization',
]


def _make_user(username, role=User.PARTICIPANT, **kwargs):
    return User.objects.create_user(
        username=username, password='pass1234', role=role,
        email=f'{username}@example.com', **kwargs
    )


def _make_event(organizer, **kwargs):
    # Always unique — Category.slug is unique, and a name derived only from
    # organizer/title could still collide across setUp() calls in different
    # test classes reusing the same title default.
    category = Category.objects.create(name=f'Cat-{uuid.uuid4().hex[:10]}')
    defaults = dict(
        title=f"Event by {organizer.username}",
        description='desc',
        organizer=organizer,
        category=category,
        location='Test Hall',
        start_date=timezone.now() + timedelta(days=1),
        end_date=timezone.now() + timedelta(days=1, hours=2),
        capacity=100,
        price=0,
        status='published',
    )
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


class ReportScopingTests(TestCase):
    """The permission-scoping behavior praised in the earlier audit —
    verified here as an executable regression test rather than a one-off
    manual check.
    """

    def setUp(self):
        self.organizer_a = _make_user('report_org_a', role=User.ORGANIZER)
        self.organizer_b = _make_user('report_org_b', role=User.ORGANIZER)
        self.staff = _make_user('report_staff', role=User.STAFF)
        self.participant = _make_user('report_participant', role=User.PARTICIPANT)

        self.event_a = _make_event(self.organizer_a, title='Org A Event')
        self.event_b = _make_event(self.organizer_b, title='Org B Event')

        Registration.objects.create(
            event=self.event_a, user=self.participant, status='confirmed'
        )
        self.client = Client()

    def test_participant_cannot_reach_report_hub(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('reports:report_hub'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_can_reach_report_hub(self):
        self.client.force_login(self.organizer_a)
        response = self.client.get(reverse('reports:report_hub'))
        self.assertEqual(response.status_code, 200)

    def test_organizer_only_sees_own_events_in_hub(self):
        self.client.force_login(self.organizer_a)
        response = self.client.get(reverse('reports:report_hub'))
        events_in_context = list(response.context['events'])
        self.assertIn(self.event_a, events_in_context)
        self.assertNotIn(self.event_b, events_in_context)
        self.assertFalse(response.context['is_system_wide'])

    def test_staff_sees_all_events_in_hub(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('reports:report_hub'))
        events_in_context = list(response.context['events'])
        self.assertIn(self.event_a, events_in_context)
        self.assertIn(self.event_b, events_in_context)
        self.assertTrue(response.context['is_system_wide'])

    def test_organizer_requesting_another_organizers_event_report_gets_404(self):
        self.client.force_login(self.organizer_a)
        url = reverse('reports:report_for_event', kwargs={
            'report_type': 'attendance', 'slug': self.event_b.slug,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_organizer_can_view_own_events_report(self):
        self.client.force_login(self.organizer_a)
        url = reverse('reports:report_for_event', kwargs={
            'report_type': 'attendance', 'slug': self.event_a.slug,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_unknown_report_type_is_404(self):
        self.client.force_login(self.organizer_a)
        url = reverse('reports:report', kwargs={'report_type': 'not_a_real_report'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_aggregate_report_only_includes_organizers_own_events(self):
        """An Organizer's system-wide (no slug) report must not leak
        another organizer's rows into the aggregate numbers.
        """
        self.client.force_login(self.organizer_a)
        url = reverse('reports:report', kwargs={'report_type': 'event_summary'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        rows = response.context['report']['rows']
        titles = [row[0] for row in rows]
        self.assertIn(self.event_a.title, titles)
        self.assertNotIn(self.event_b.title, titles)


class ReportExportTests(TestCase):
    """Every report type, exported in every supported format, must return
    a well-formed, correctly-typed file — not just render an HTML page.
    """

    def setUp(self):
        self.organizer = _make_user('export_org', role=User.ORGANIZER)
        self.event = _make_event(self.organizer, title='Export Test Event')
        self.participant = _make_user('export_participant', role=User.PARTICIPANT)
        Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        self.client = Client()
        self.client.force_login(self.organizer)

    def test_csv_export_for_every_report_type(self):
        for report_type in REPORT_TYPES:
            with self.subTest(report_type=report_type):
                url = reverse('reports:report', kwargs={'report_type': report_type})
                response = self.client.get(url, {'format': 'csv'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'text/csv')
                self.assertIn('attachment', response['Content-Disposition'])
                content = response.content.decode('utf-8')
                self.assertTrue(len(content) > 0)

    @unittest.skipUnless(HAS_OPENPYXL, "openpyxl not installed in this environment")
    def test_xlsx_export_for_every_report_type(self):
        for report_type in REPORT_TYPES:
            with self.subTest(report_type=report_type):
                url = reverse('reports:report', kwargs={'report_type': report_type})
                response = self.client.get(url, {'format': 'xlsx'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response['Content-Type'],
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                self.assertTrue(response.content.startswith(b'PK'))

    @unittest.skipUnless(HAS_OPENPYXL, "openpyxl not installed in this environment")
    def test_xlsx_export_survives_slash_in_report_title(self):
        """Regression test: the Financial report's title is 'Revenue /
        Expense / Profit-Loss Report'. openpyxl forbids \\/*?:[] in a
        worksheet title, so a raw slice of that title crashes the export.
        This is exactly the report_type that previously raised
        ValueError: Invalid character / found in sheet title.
        """
        url = reverse('reports:report', kwargs={'report_type': 'financial'})
        response = self.client.get(url, {'format': 'xlsx'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'PK'))

    @unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed in this environment")
    def test_pdf_export_for_every_report_type(self):
        for report_type in REPORT_TYPES:
            with self.subTest(report_type=report_type):
                url = reverse('reports:report', kwargs={'report_type': report_type})
                response = self.client.get(url, {'format': 'pdf'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertTrue(response.content.startswith(b'%PDF'))

    def test_attendance_report_reflects_real_checkin_activity(self):
        """Cross-app correctness check: a ticket scanned via the tickets
        app's real check-in endpoint must show up in the reports app's
        attendance numbers, since reports has no models of its own and
        derives everything live from tickets.CheckInLog.
        """
        ticket = Ticket.objects.get(registration__event=self.event)
        self.client.post(
            reverse('tickets:check_in', kwargs={'slug': self.event.slug}),
            {'token': ticket.qr_token},
        )
        url = reverse('reports:report', kwargs={'report_type': 'attendance'})
        response = self.client.get(url)
        summary = dict(response.context['report']['summary'])
        self.assertEqual(summary['Checked In'], 1)

    def test_html_report_view_status_ok_for_every_report_type(self):
        for report_type in REPORT_TYPES:
            with self.subTest(report_type=report_type):
                url = reverse('reports:report', kwargs={'report_type': report_type})
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)


class AnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.organizer = _make_user('analytics_org', role=User.ORGANIZER)
        self.participant = _make_user('analytics_participant', role=User.PARTICIPANT)
        self.client = Client()

    def test_participant_denied(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('reports:analytics_dashboard'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_allowed(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('reports:analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
