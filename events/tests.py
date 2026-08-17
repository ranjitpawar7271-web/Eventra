from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User
from .ics_utils import build_google_calendar_url, build_ics_bytes
from .models import Event


def make_event(organizer, title='Test Event, With Comma'):
    now = timezone.now()
    return Event.objects.create(
        title=title,
        description='Line one.\nLine two; with a semicolon, and a comma.',
        organizer=organizer,
        location='Community Hall, Main St',
        start_date=now + timedelta(days=10),
        end_date=now + timedelta(days=10, hours=3),
        capacity=100,
        price=0,
    )


class ICSExportTests(TestCase):
    """Covers events/ics_utils.py — the Module 10 'Export to Google
    Calendar' feature. No new Django app: this is a small, tightly
    scoped addition to the existing events app rather than something
    that warranted its own models/urls.
    """

    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.event = make_event(self.organizer)

    def test_ics_bytes_are_well_formed(self):
        ics = build_ics_bytes(self.event).decode('utf-8')
        self.assertTrue(ics.startswith('BEGIN:VCALENDAR\r\n'))
        self.assertTrue(ics.rstrip('\r\n').endswith('END:VCALENDAR'))
        self.assertIn('BEGIN:VEVENT', ics)
        self.assertIn('END:VEVENT', ics)
        self.assertIn(f'UID:event-{self.event.id}@eventra', ics)

    def test_ics_escapes_special_characters(self):
        ics = build_ics_bytes(self.event).decode('utf-8')
        # Comma in title/location must be escaped, not left raw.
        self.assertIn('Test Event\\, With Comma', ics)
        self.assertIn('Community Hall\\, Main St', ics)
        # Semicolon and embedded newline in description must be escaped.
        self.assertIn('Line one.\\nLine two\\; with a semicolon\\, and a comma.', ics)

    def test_ics_uses_crlf_line_endings(self):
        ics = build_ics_bytes(self.event).decode('utf-8')
        self.assertIn('\r\n', ics)
        # No bare \n without a preceding \r anywhere in the structural lines
        # (the escaped \n inside DESCRIPTION is literal backslash-n text,
        # not an actual line break, so it doesn't count here).
        for line in ics.split('\r\n')[:-1]:
            self.assertNotIn('\n', line)

    def test_google_calendar_url_contains_event_details(self):
        url = build_google_calendar_url(self.event)
        self.assertTrue(url.startswith('https://calendar.google.com/calendar/render?'))
        self.assertIn('action=TEMPLATE', url)

    def test_ics_download_view_is_public_and_returns_calendar_file(self):
        # No login at all.
        response = self.client.get(reverse('events:event_ics', kwargs={'slug': self.event.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/calendar; charset=utf-8')
        self.assertIn(f'{self.event.slug}.ics', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'BEGIN:VCALENDAR'))

    def test_event_detail_includes_google_calendar_url(self):
        response = self.client.get(reverse('events:event_detail', kwargs={'slug': self.event.slug}))
        self.assertIn('google_calendar_url', response.context)
        self.assertTrue(response.context['google_calendar_url'].startswith('https://calendar.google.com/'))


class EventTemplateTests(TestCase):
    """Covers events/event_templates.py — the Module 10 'Event Templates'
    feature. Plain presets, not a database model (see the module docstring
    for why); these tests confirm the presets actually flow into the
    create form's initial values, not just that the dict exists."""

    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)

    def test_unknown_template_key_returns_none(self):
        from .event_templates import get_template_initial
        self.assertIsNone(get_template_initial('not-a-real-template'))
        self.assertIsNone(get_template_initial(''))

    def test_known_template_returns_prefill_dict(self):
        from .event_templates import get_template_initial
        initial = get_template_initial('hackathon')
        self.assertEqual(initial['title'], '[Theme] Hackathon')
        self.assertEqual(initial['capacity'], 120)
        self.assertEqual(initial['price'], 0)

    def test_create_form_prefilled_when_template_param_given(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('events:event_create') + '?template=wedding')
        self.assertEqual(response.context['form'].initial['title'], "[Names]'s Wedding Celebration")
        self.assertEqual(response.context['form'].initial['capacity'], 100)

    def test_create_form_blank_without_template_param(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('events:event_create'))
        self.assertNotIn('title', response.context['form'].initial)

    def test_create_form_blank_for_unknown_template_param(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('events:event_create') + '?template=not-real')
        self.assertFalse(response.context['form'].initial)

    def test_picker_page_requires_event_management_permission(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('events:event_create_start'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('events:event_create_start'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('conference', response.context['templates'])

    def test_template_prefill_does_not_bypass_required_field_validation(self):
        """A template only sets initial values for a GET request — it
        must not let a POST skip required fields like category/dates."""
        self.client.login(username='org1', password='pw12345!')
        response = self.client.post(reverse('events:event_create'), {})
        self.assertEqual(response.status_code, 200)  # re-rendered with errors, not saved
        self.assertTrue(response.context['form'].errors)
