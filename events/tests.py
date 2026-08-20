import importlib.util
import unittest
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User
from .ics_utils import build_google_calendar_url, build_ics_bytes
from .models import Event, Registration, WaitlistEntry
from . import waitlist_services

HAS_QRCODE = importlib.util.find_spec('qrcode') is not None


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


def make_status_event(organizer, title, status='published', start_offset_days=10,
                       duration_hours=3, capacity=100, price=0):
    """Like `make_event`, but with the status/timing knobs the
    registration-hardening tests need to exercise draft/cancelled/
    completed/past events directly, instead of only the default
    "10 days out, published" fixture.
    """
    now = timezone.now()
    start = now + timedelta(days=start_offset_days)
    return Event.objects.create(
        title=title,
        description='A test event.',
        organizer=organizer,
        location='Community Hall',
        start_date=start,
        end_date=start + timedelta(hours=duration_hours),
        capacity=capacity,
        price=price,
        status=status,
    )


class RegistrationWorkflowSecurityTests(TestCase):
    """Covers the registration/waitlist hardening: server-side enforcement
    of HTTP method and event lifecycle, so a direct URL hit or crafted
    request can't do what the UI alone was preventing.
    """

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='org1', password='pw12345!', role=User.ORGANIZER
        )
        self.participant = User.objects.create_user(
            username='part1', password='pw12345!', role=User.PARTICIPANT
        )

    def _login(self):
        self.client.login(username='part1', password='pw12345!')

    def _register_url(self, event):
        return reverse('events:event_register', kwargs={'slug': event.slug})

    def _join_waitlist_url(self, event):
        return reverse('events:join_waitlist', kwargs={'slug': event.slug})

    # --- Valid registration ---------------------------------------
    def test_valid_registration_succeeds_for_free_published_upcoming_event(self):
        event = make_status_event(self.organizer, 'Open Event', status='published')
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertTrue(
            Registration.objects.filter(event=event, user=self.participant, status='confirmed').exists()
        )

    # --- HTTP method enforcement ------------------------------------
    def test_get_registration_is_rejected(self):
        event = make_status_event(self.organizer, 'GET Test Event', status='published')
        self._login()
        response = self.client.get(self._register_url(event))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Registration.objects.filter(event=event, user=self.participant).exists())

    def test_get_join_waitlist_is_rejected(self):
        event = make_status_event(self.organizer, 'GET Waitlist Event', status='published', capacity=1)
        Registration.objects.create(event=event, user=self.organizer, status='confirmed')
        self._login()
        response = self.client.get(self._join_waitlist_url(event))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(WaitlistEntry.objects.filter(event=event, user=self.participant).exists())

    # --- Event lifecycle validation ----------------------------------
    def test_draft_event_registration_rejected(self):
        event = make_status_event(self.organizer, 'Draft Event', status='draft')
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertFalse(Registration.objects.filter(event=event, user=self.participant).exists())

    def test_cancelled_event_registration_rejected(self):
        event = make_status_event(self.organizer, 'Cancelled Event', status='cancelled')
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertFalse(Registration.objects.filter(event=event, user=self.participant).exists())

    def test_completed_event_registration_rejected(self):
        event = make_status_event(
            self.organizer, 'Completed Event', status='completed', start_offset_days=-10
        )
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertFalse(Registration.objects.filter(event=event, user=self.participant).exists())

    def test_past_event_registration_rejected(self):
        # Still "published" but its start_date has already passed — must
        # be rejected even though status alone looks fine.
        event = make_status_event(
            self.organizer, 'Past Event', status='published', start_offset_days=-5
        )
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertFalse(Registration.objects.filter(event=event, user=self.participant).exists())

    def test_already_started_event_registration_rejected(self):
        # start_date in the past, end_date in the future: event is
        # currently ongoing, not merely "past" — must still be rejected.
        now = timezone.now()
        event = Event.objects.create(
            title='Ongoing Event', description='desc', organizer=self.organizer,
            location='Hall', start_date=now - timedelta(hours=1), end_date=now + timedelta(hours=2),
            capacity=50, price=0, status='published',
        )
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertFalse(Registration.objects.filter(event=event, user=self.participant).exists())

    # --- Duplicate registration ---------------------------------------
    def test_duplicate_registration_rejected(self):
        event = make_status_event(self.organizer, 'Dup Event', status='published')
        self._login()
        self.client.post(self._register_url(event))
        self.client.post(self._register_url(event))
        self.assertEqual(
            Registration.objects.filter(event=event, user=self.participant).count(), 1
        )

    def test_duplicate_registration_blocked_at_db_level(self):
        event = make_status_event(self.organizer, 'DB Constraint Event', status='published')
        Registration.objects.create(event=event, user=self.participant, status='confirmed')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Registration.objects.create(event=event, user=self.participant, status='confirmed')

    # --- Full event ------------------------------------------------
    def test_full_event_registration_redirects_to_waitlist_prompt_without_registering(self):
        event = make_status_event(self.organizer, 'Full Event', status='published', capacity=1)
        Registration.objects.create(event=event, user=self.organizer, status='confirmed')
        self._login()
        response = self.client.post(self._register_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertFalse(
            Registration.objects.filter(event=event, user=self.participant, status='confirmed').exists()
        )

    # --- Waitlist ----------------------------------------------------
    def test_valid_waitlist_join_on_full_open_event(self):
        event = make_status_event(self.organizer, 'Waitlist Event', status='published', capacity=1)
        Registration.objects.create(event=event, user=self.organizer, status='confirmed')
        self._login()
        response = self.client.post(self._join_waitlist_url(event))
        self.assertRedirects(response, reverse('events:event_detail', kwargs={'slug': event.slug}))
        self.assertTrue(
            WaitlistEntry.objects.filter(
                event=event, user=self.participant, status=WaitlistEntry.STATUS_WAITING
            ).exists()
        )

    def test_waitlist_join_rejected_for_cancelled_event(self):
        event = make_status_event(self.organizer, 'Cancelled Waitlist Event', status='cancelled')
        self._login()
        self.client.post(self._join_waitlist_url(event))
        self.assertFalse(WaitlistEntry.objects.filter(event=event, user=self.participant).exists())

    def test_waitlist_join_rejected_for_completed_event(self):
        event = make_status_event(
            self.organizer, 'Completed Waitlist Event', status='completed', start_offset_days=-10
        )
        self._login()
        self.client.post(self._join_waitlist_url(event))
        self.assertFalse(WaitlistEntry.objects.filter(event=event, user=self.participant).exists())

    def test_waitlist_join_rejected_for_past_event(self):
        event = make_status_event(
            self.organizer, 'Past Waitlist Event', status='published', start_offset_days=-5
        )
        self._login()
        self.client.post(self._join_waitlist_url(event))
        self.assertFalse(WaitlistEntry.objects.filter(event=event, user=self.participant).exists())

    def test_waitlist_service_rejects_direct_call_for_closed_event(self):
        # Defense-in-depth: the service function itself refuses, not just
        # the view — covers any other caller that might bypass the view.
        event = make_status_event(self.organizer, 'Direct Call Event', status='cancelled')
        entry, created = waitlist_services.join_waitlist(event, self.participant)
        self.assertIsNone(entry)
        self.assertFalse(created)

    # --- Unauthorized / unauthenticated -------------------------------
    def test_anonymous_registration_redirects_to_login(self):
        event = make_status_event(self.organizer, 'Anon Event', status='published')
        response = self.client.post(self._register_url(event))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:login'), response.url)
        self.assertFalse(Registration.objects.filter(event=event).exists())

    def test_anonymous_join_waitlist_redirects_to_login(self):
        event = make_status_event(self.organizer, 'Anon Waitlist Event', status='published', capacity=1)
        Registration.objects.create(event=event, user=self.organizer, status='confirmed')
        response = self.client.post(self._join_waitlist_url(event))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:login'), response.url)
        self.assertFalse(WaitlistEntry.objects.filter(event=event).exists())


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


class RegistrationQRTests(TestCase):
    """Covers the Registration QR + shareable link feature.

    This is deliberately NOT a new registration system: `event_registration_qr`
    (events/views.py) just renders a PNG of `event.get_absolute_url()` — the
    same public event-detail page that already has the Register/Join Waitlist
    form on it (see templates/events/event_detail.html). So "scan the QR",
    "click a shared link", and "click the event from the list" are all the
    same HTTP GET to the same view; the only new code is the PNG rendering,
    reusing tickets/utils.py::render_qr_png (no second QR library, no
    QR-specific registration path). Capacity/lifecycle/duplicate rules are
    exercised in full by RegistrationWorkflowSecurityTests above; the tests
    here focus on what's actually new: the QR endpoint itself, and that it
    leads into the one real registration flow rather than a parallel one.
    """

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='qr_org', password='pw12345!', role=User.ORGANIZER
        )
        self.participant = User.objects.create_user(
            username='qr_part', password='pw12345!', role=User.PARTICIPANT
        )
        self.event = make_status_event(self.organizer, 'QR Event', status='published')

    def _qr_url(self, event):
        return reverse('events:event_registration_qr', kwargs={'slug': event.slug})

    # --- Event creation generates a usable registration URL + QR --------
    def test_event_creation_yields_working_registration_url_and_qr_endpoint(self):
        self.assertEqual(self.event.get_absolute_url(), f'/events/{self.event.slug}/')
        self.assertTrue(self.event.get_registration_qr_url().endswith('/registration-qr/'))
        response = self.client.get(self._qr_url(self.event))
        self.assertEqual(response.status_code, 200)

    @unittest.skipUnless(HAS_QRCODE, "qrcode not installed in this environment")
    def test_qr_endpoint_returns_a_real_png(self):
        response = self.client.get(self._qr_url(self.event))
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    @unittest.skipUnless(HAS_QRCODE, "qrcode not installed in this environment")
    def test_qr_encodes_the_events_own_absolute_registration_url(self):
        """The PNG must encode the event-detail URL, not ticket data or
        anything else — rendering is deterministic, so re-rendering the
        exact URL we expect and comparing bytes proves what's inside
        without needing a separate QR-decoding dependency."""
        from tickets.utils import render_qr_png

        response = self.client.get(self._qr_url(self.event))
        expected_url = 'http://testserver' + self.event.get_absolute_url()
        expected_png = render_qr_png(expected_url)
        self.assertEqual(response.content, expected_png)

    def test_qr_endpoint_404s_for_unknown_event(self):
        response = self.client.get('/events/no-such-event-slug/registration-qr/')
        self.assertEqual(response.status_code, 404)

    # --- Public / shareable: no login required to reach or scan it ------
    def test_registration_qr_and_link_are_reachable_without_login(self):
        qr_response = self.client.get(self._qr_url(self.event))
        self.assertEqual(qr_response.status_code, 200)

        link_response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(link_response.status_code, 200)
        self.assertEqual(link_response.context['event'], self.event)

    # --- The link is the real registration entry point, not a copy ------
    def test_scanning_link_then_registering_uses_the_existing_registration_endpoint(self):
        """Simulates the actual QR flow end to end: open the link the QR
        encodes, then submit the same Register form that page renders —
        landing on a real, existing Registration row through the existing
        endpoint, with no separate QR-only code path involved."""
        self.client.login(username='qr_part', password='pw12345!')

        detail_response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Register Now')

        register_response = self.client.post(
            reverse('events:event_register', kwargs={'slug': self.event.slug})
        )
        self.assertRedirects(register_response, self.event.get_absolute_url())
        self.assertTrue(
            Registration.objects.filter(
                event=self.event, user=self.participant, status='confirmed'
            ).exists()
        )

    def test_anonymous_scan_reaches_login_prompt_without_losing_event_context(self):
        """An unauthenticated scan must not 404 or silently register —
        it lands on the same public page, which prompts login with
        `?next=` back to this exact event (existing behavior in
        templates/events/event_detail.html), not a dead end."""
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login to Register')
        self.assertContains(response, reverse('users:login'))

    # --- Existing lifecycle/capacity rules still apply via this entry point
    def test_link_for_cancelled_event_still_blocks_registration_server_side(self):
        cancelled = make_status_event(self.organizer, 'Cancelled QR Event', status='cancelled')
        self.client.login(username='qr_part', password='pw12345!')

        # The link/QR still opens (it's just the public detail page)...
        detail_response = self.client.get(cancelled.get_absolute_url())
        self.assertEqual(detail_response.status_code, 200)

        # ...but the existing server-side lifecycle check still rejects
        # the registration itself — the QR is not a bypass.
        register_response = self.client.post(
            reverse('events:event_register', kwargs={'slug': cancelled.slug})
        )
        self.assertRedirects(register_response, cancelled.get_absolute_url())
        self.assertFalse(
            Registration.objects.filter(event=cancelled, user=self.participant).exists()
        )

    # --- Organizer-only QR management panel ------------------------------
    def test_organizer_sees_registration_qr_management_panel(self):
        self.client.login(username='qr_org', password='pw12345!')
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, 'Registration QR')
        self.assertContains(response, self._qr_url(self.event))

    def test_participant_does_not_see_organizer_qr_management_panel(self):
        self.client.login(username='qr_part', password='pw12345!')
        response = self.client.get(self.event.get_absolute_url())
        self.assertNotContains(response, 'Registration QR')

    def test_unauthorized_user_cannot_reach_organizer_only_pages_via_qr_link(self):
        """Knowing the (public) registration link/QR must not grant access
        to organizer-only management views like the participants list."""
        self.client.login(username='qr_part', password='pw12345!')
        response = self.client.get(
            reverse('events:event_participants', kwargs={'slug': self.event.slug})
        )
        self.assertEqual(response.status_code, 302)


@unittest.skipUnless(
    importlib.util.find_spec('qrcode') is not None, "qrcode not installed in this environment"
)
class RegistrationQRPaidEventTests(TestCase):
    """Confirms the registration QR feature composes correctly with the
    existing paid-event -> payment -> ticket -> ticket-QR pipeline, and
    that the two QR systems (registration vs. ticket) never collide.
    """

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='qr_paid_org', password='pw12345!', role=User.ORGANIZER
        )
        self.participant = User.objects.create_user(
            username='qr_paid_part', password='pw12345!', role=User.PARTICIPANT
        )
        self.event = make_status_event(
            self.organizer, 'Paid QR Event', status='published', price=250
        )

    def test_paid_event_registration_via_link_leads_to_checkout_not_direct_ticket(self):
        """Per spec: the ticket (and its own QR) must NOT be generated at
        event-creation or QR-scan time — only after payment succeeds."""
        from payments.models import Payment
        from tickets.models import Ticket

        self.client.login(username='qr_paid_part', password='pw12345!')
        self.client.get(self.event.get_absolute_url())  # the "scan"

        response = self.client.post(
            reverse('events:event_register', kwargs={'slug': self.event.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/payments/', response.url)

        registration = Registration.objects.get(event=self.event, user=self.participant)
        self.assertEqual(registration.status, 'pending_payment')
        self.assertFalse(Ticket.objects.filter(registration=registration).exists())

    def test_successful_payment_still_issues_a_distinct_ticket_qr(self):
        """After payment, the existing ticket pipeline must still fire
        normally, and its QR payload must be unrelated to (and unable to
        be reconstructed from) the public registration QR/link."""
        from payments import services as payment_services
        from payments.models import Payment
        from tickets.models import Ticket
        from tickets.utils import render_qr_png

        registration = Registration.objects.create(
            event=self.event, user=self.participant, status='pending_payment'
        )
        payment = payment_services.get_or_create_pending_payment(registration)
        payment_services.process_mock_payment(payment, Payment.METHOD_CARD)

        registration.refresh_from_db()
        self.assertEqual(registration.status, 'confirmed')

        ticket = Ticket.objects.get(registration=registration)
        self.assertTrue(ticket.qr_token)

        registration_qr_png = render_qr_png(
            'http://testserver' + self.event.get_absolute_url()
        )
        ticket_qr_png = render_qr_png(ticket.qr_token)
        self.assertNotEqual(registration_qr_png, ticket_qr_png)