"""
Real, executable coverage for the tickets app (Module 7).

Before this file existed, tickets/tests.py was empty and reports/tests.py
was Django's default boilerplate — 0 real tests for either module, versus
11-21 tests each for every other module. That gap is exactly how the
`ticket.event_id` AttributeError (see TicketScanEndpointTests.test_checkin_success)
shipped without being caught: nothing ever drove a scan through the real
HTTP endpoint.

Run with:
    python manage.py test tickets

QR-image/PDF tests are skipped automatically if `qrcode` / `reportlab`
aren't installed, matching a bare `pip install -r requirements.txt`
environment before the optional export packages are added — see the
`skipUnless` guards below rather than stubbing those packages out.
"""
import importlib.util
import threading
import unittest
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from categories.models import Category
from workflow.models import Notification
from .models import CheckInLog, Ticket, QR_SALT

User = get_user_model()

HAS_QRCODE = importlib.util.find_spec('qrcode') is not None
HAS_REPORTLAB = importlib.util.find_spec('reportlab') is not None


def _make_user(username, role=User.PARTICIPANT, **kwargs):
    return User.objects.create_user(
        username=username, password='pass1234', role=role,
        email=f'{username}@example.com', **kwargs
    )


def _make_event(organizer, **kwargs):
    # Always unique, even across multiple events for the same organizer in
    # one test — Category.slug is unique, and reusing `organizer.username`
    # alone collided the second time _make_event() was called for the same
    # organizer (e.g. one test creating a free event and a paid event).
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


class TicketAutoIssuanceTests(TestCase):
    """The core Module 7 promise: a Ticket appears with no manual step the
    moment a Registration becomes confirmed, and disappears (cancels) the
    same way — driven entirely by the post_save signal in signals.py.
    """

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.participant = _make_user('participant1', role=User.PARTICIPANT)
        self.event = _make_event(self.organizer)

    def test_confirmed_registration_auto_issues_ticket(self):
        self.assertFalse(Ticket.objects.filter(registration__event=self.event).exists())
        reg = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        ticket = Ticket.objects.get(registration=reg)
        self.assertEqual(ticket.status, Ticket.STATUS_ISSUED)
        self.assertTrue(ticket.ticket_code.startswith('EVS-'))
        self.assertTrue(ticket.qr_token)

    def test_free_event_issues_free_ticket_paid_event_issues_paid(self):
        reg_free = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        self.assertEqual(Ticket.objects.get(registration=reg_free).ticket_type, Ticket.TYPE_FREE)

        paid_event = _make_event(self.organizer, price=500)
        other_user = _make_user('participant2')
        reg_paid = Registration.objects.create(
            event=paid_event, user=other_user, status='confirmed'
        )
        self.assertEqual(Ticket.objects.get(registration=reg_paid).ticket_type, Ticket.TYPE_PAID)

    def test_cancelling_registration_cancels_unused_ticket(self):
        reg = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        reg.status = 'cancelled'
        reg.save(update_fields=['status'])
        ticket = Ticket.objects.get(registration=reg)
        self.assertEqual(ticket.status, Ticket.STATUS_CANCELLED)

    def test_cancelling_does_not_touch_already_checked_in_ticket(self):
        reg = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        ticket = Ticket.objects.get(registration=reg)
        ticket.status = Ticket.STATUS_CHECKED_IN
        ticket.save(update_fields=['status'])

        reg.status = 'cancelled'
        reg.save(update_fields=['status'])
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_CHECKED_IN)

    def test_re_registering_after_cancel_revives_same_ticket_code(self):
        reg = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        original_ticket = Ticket.objects.get(registration=reg)
        original_code = original_ticket.ticket_code

        reg.status = 'cancelled'
        reg.save(update_fields=['status'])
        reg.status = 'confirmed'
        reg.save(update_fields=['status'])

        self.assertEqual(Ticket.objects.filter(registration=reg).count(), 1)
        revived = Ticket.objects.get(registration=reg)
        self.assertEqual(revived.ticket_code, original_code)
        self.assertEqual(revived.status, Ticket.STATUS_ISSUED)

    def test_stale_reverse_relation_cache_does_not_hide_new_ticket(self):
        """Regression test for the Django gotcha signals.py now guards
        against: touching `registration.ticket` on an instance *before* a
        Ticket exists must not make a later access on that same instance
        blind to a Ticket created afterwards via a signal.
        """
        # Start the registration as 'cancelled' so no ticket exists yet;
        # the signal only issues one on 'confirmed'.
        reg = Registration.objects.create(
            event=self.event, user=self.participant, status='cancelled'
        )
        # Deliberately poke the reverse descriptor before a ticket exists,
        # simulating upstream code that checked too early.
        with self.assertRaises(Ticket.DoesNotExist):
            reg.ticket

        reg.status = 'confirmed'
        reg.save(update_fields=['status'])  # signal creates the Ticket

        # If the negative lookup got cached on `reg`, this would still
        # raise DoesNotExist even though a Ticket now exists in the DB.
        self.assertIsNotNone(Ticket.objects.filter(registration=reg).first())


class TicketScanEndpointTests(TestCase):
    """Drives the real HTTP scan endpoints — this is what would have
    caught the `ticket.event_id` AttributeError immediately.
    """

    def setUp(self):
        self.organizer = _make_user('organizer2', role=User.ORGANIZER)
        self.other_organizer = _make_user('organizer3', role=User.ORGANIZER)
        self.staff = _make_user('staffmember', role=User.STAFF)
        self.participant = _make_user('participant3', role=User.PARTICIPANT)

        self.event = _make_event(self.organizer)
        self.other_event = _make_event(self.other_organizer)

        self.reg = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        self.ticket = Ticket.objects.get(registration=self.reg)

        self.client = Client()

    def _checkin(self, user, event, token):
        self.client.force_login(user)
        return self.client.post(
            reverse('tickets:check_in', kwargs={'slug': event.slug}),
            {'token': token},
        )

    def _checkout(self, user, event, token):
        self.client.force_login(user)
        return self.client.post(
            reverse('tickets:check_out', kwargs={'slug': event.slug}),
            {'token': token},
        )

    def test_checkin_success(self):
        """This is the exact path that previously 500'd with
        AttributeError: 'Ticket' object has no attribute 'event_id'.
        """
        response = self._checkin(self.organizer, self.event, self.ticket.qr_token)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['result'], 'checked_in')

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.STATUS_CHECKED_IN)
        self.assertIsNotNone(self.ticket.checked_in_at)
        self.assertEqual(self.ticket.checked_in_by, self.organizer)
        self.assertTrue(
            CheckInLog.objects.filter(
                event=self.event, ticket=self.ticket, result=CheckInLog.RESULT_CHECKED_IN
            ).exists()
        )

    def test_duplicate_scan_is_rejected_and_logged(self):
        self._checkin(self.organizer, self.event, self.ticket.qr_token)
        response = self._checkin(self.organizer, self.event, self.ticket.qr_token)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['result'], 'duplicate')
        self.assertTrue(
            CheckInLog.objects.filter(
                event=self.event, ticket=self.ticket, result=CheckInLog.RESULT_DUPLICATE
            ).exists()
        )

    def test_forged_token_is_rejected(self):
        forged = signing.dumps(self.ticket.ticket_code, salt='wrong-salt')
        response = self._checkin(self.organizer, self.event, forged)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['result'], 'invalid')
        self.assertTrue(
            CheckInLog.objects.filter(event=self.event, ticket__isnull=True,
                                       result=CheckInLog.RESULT_INVALID).exists()
        )

    def test_tampered_but_correctly_salted_token_for_nonexistent_code_is_rejected(self):
        fake = signing.dumps('EVS-DOESNOTEXIST', salt=QR_SALT)
        response = self._checkin(self.organizer, self.event, fake)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['result'], 'invalid')

    def test_ticket_for_wrong_event_is_rejected(self):
        response = self._checkin(self.other_organizer, self.other_event, self.ticket.qr_token)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['result'], 'invalid')
        self.assertIn('different event', data['message'])
        # Confirm this ticket's own status is untouched.
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.STATUS_ISSUED)

    def test_checkout_before_checkin_is_rejected(self):
        response = self._checkout(self.organizer, self.event, self.ticket.qr_token)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['result'], 'invalid')

    def test_checkin_then_checkout_success(self):
        self._checkin(self.organizer, self.event, self.ticket.qr_token)
        response = self._checkout(self.organizer, self.event, self.ticket.qr_token)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['result'], 'checked_out')

    def test_organizer_cannot_scan_for_another_organizers_event(self):
        response = self._checkin(self.other_organizer, self.event, self.ticket.qr_token)
        self.assertEqual(response.status_code, 403)

    def test_staff_can_scan_any_event(self):
        response = self._checkin(self.staff, self.event, self.ticket.qr_token)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_participant_cannot_access_scan_endpoint(self):
        response = self._checkin(self.participant, self.event, self.ticket.qr_token)
        self.assertEqual(response.status_code, 403)

    def test_cancelled_ticket_cannot_be_checked_in(self):
        self.ticket.status = Ticket.STATUS_CANCELLED
        self.ticket.save(update_fields=['status'])
        response = self._checkin(self.organizer, self.event, self.ticket.qr_token)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['result'], 'invalid')

    def test_checkin_sends_notification_to_participant(self):
        self.assertFalse(
            Notification.objects.filter(user=self.participant, notification_type=Notification.TYPE_CHECKIN).exists()
        )
        self._checkin(self.organizer, self.event, self.ticket.qr_token)
        self.assertTrue(
            Notification.objects.filter(
                user=self.participant, notification_type=Notification.TYPE_CHECKIN,
                dedupe_key=f'checkin-confirmed-{self.ticket.pk}',
            ).exists()
        )

    def test_anonymous_scan_request_is_rejected(self):
        # No force_login — the scan endpoints require an authenticated
        # scanner (@login_required), never mind ticket-manage permission.
        response = self.client.post(
            reverse('tickets:check_in', kwargs={'slug': self.event.slug}),
            {'token': self.ticket.qr_token},
        )
        self.assertEqual(response.status_code, 302)  # redirected to login
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.STATUS_ISSUED)


class TicketCheckinConcurrencyTests(TransactionTestCase):
    """Covers the race condition fix directly: two scanners (two staff
    devices, or a flaky client retry landing twice) hitting check-in for
    the *same* ticket at almost the same instant must not both succeed.

    Needs TransactionTestCase (not TestCase) — TestCase wraps each test
    in one outer transaction and effectively serializes everything
    through it, which would hide exactly the race we're trying to prove
    is closed. TransactionTestCase lets the two threads' requests run as
    genuinely separate, concurrently-committing transactions.
    """

    def setUp(self):
        self.organizer = _make_user('conc_organizer', role=User.ORGANIZER)
        self.staff = _make_user('conc_staff', role=User.STAFF)
        self.participant = _make_user('conc_participant', role=User.PARTICIPANT)
        self.event = _make_event(self.organizer)
        self.reg = Registration.objects.create(
            event=self.event, user=self.participant, status='confirmed'
        )
        self.ticket = Ticket.objects.get(registration=self.reg)

    def _concurrent_scan(self, url, users):
        """POST `url` once per user in `users`, all released from a
        shared barrier at (as close as threading allows) the same
        instant. Returns the parsed JSON body from each request, in
        completion order.

        Login happens up front, outside the barrier: force_login() does
        its own session-table write, and racing *that* between threads
        is a session-backend contention issue, not the ticket-check-in
        race this test exists to prove — synchronizing only the POST
        keeps the test focused on the actual thing being verified.
        """
        clients = []
        for user in users:
            client = Client()
            client.force_login(user)
            clients.append(client)

        results = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(len(users))

        def worker(client):
            barrier.wait(timeout=5)
            response = client.post(url, {'token': self.ticket.qr_token})
            with results_lock:
                results.append(response.json())

        threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        return results

    def test_simultaneous_checkin_only_one_succeeds(self):
        url = reverse('tickets:check_in', kwargs={'slug': self.event.slug})
        results = self._concurrent_scan(url, [self.organizer, self.staff])

        self.assertEqual(len(results), 2)
        successes = [r for r in results if r.get('success')]
        duplicates = [r for r in results if r.get('result') == 'duplicate']
        self.assertEqual(len(successes), 1, f"expected exactly 1 success, got: {results}")
        self.assertEqual(len(duplicates), 1, f"expected exactly 1 duplicate, got: {results}")

        # The ticket itself ends up checked in exactly once...
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.STATUS_CHECKED_IN)

        # ...and the audit trail agrees: one real check-in, one rejected
        # duplicate — never two successful CheckInLog rows for the same
        # ticket.
        self.assertEqual(
            CheckInLog.objects.filter(ticket=self.ticket, result=CheckInLog.RESULT_CHECKED_IN).count(), 1
        )
        self.assertEqual(
            CheckInLog.objects.filter(ticket=self.ticket, result=CheckInLog.RESULT_DUPLICATE).count(), 1
        )

    def test_simultaneous_checkout_only_one_succeeds(self):
        # Get the ticket checked in first (not part of what's being raced).
        client = Client()
        client.force_login(self.organizer)
        client.post(
            reverse('tickets:check_in', kwargs={'slug': self.event.slug}),
            {'token': self.ticket.qr_token},
        )

        url = reverse('tickets:check_out', kwargs={'slug': self.event.slug})
        results = self._concurrent_scan(url, [self.organizer, self.staff])

        successes = [r for r in results if r.get('success')]
        duplicates = [r for r in results if r.get('result') == 'duplicate']
        self.assertEqual(len(successes), 1, f"expected exactly 1 success, got: {results}")
        self.assertEqual(len(duplicates), 1, f"expected exactly 1 duplicate, got: {results}")

        self.assertEqual(
            CheckInLog.objects.filter(ticket=self.ticket, result=CheckInLog.RESULT_CHECKED_OUT).count(), 1
        )


class TicketViewPermissionTests(TestCase):
    def setUp(self):
        self.organizer = _make_user('organizer4', role=User.ORGANIZER)
        self.other_participant = _make_user('nosy_participant', role=User.PARTICIPANT)
        self.owner = _make_user('ticket_owner', role=User.PARTICIPANT)
        self.event = _make_event(self.organizer)
        self.reg = Registration.objects.create(
            event=self.event, user=self.owner, status='confirmed'
        )
        self.ticket = Ticket.objects.get(registration=self.reg)
        self.client = Client()

    def test_owner_can_view_own_ticket(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse('tickets:ticket_detail', kwargs={'ticket_code': self.ticket.ticket_code})
        )
        self.assertEqual(response.status_code, 200)

    def test_other_participant_cannot_view_someone_elses_ticket(self):
        self.client.force_login(self.other_participant)
        response = self.client.get(
            reverse('tickets:ticket_detail', kwargs={'ticket_code': self.ticket.ticket_code})
        )
        # Permission check redirects rather than 403/404 for this view.
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_can_view_ticket_for_their_own_event(self):
        self.client.force_login(self.organizer)
        response = self.client.get(
            reverse('tickets:ticket_detail', kwargs={'ticket_code': self.ticket.ticket_code})
        )
        self.assertEqual(response.status_code, 200)


class TicketExportEndpointTests(TestCase):
    """QR-image/PDF tests only run when the optional packages are actually
    installed, mirroring a bare `pip install -r requirements.txt` before
    qrcode/reportlab are added — skip, don't stub, so a skip in CI output
    honestly reflects what wasn't exercised.
    """

    def setUp(self):
        self.organizer = _make_user('organizer5', role=User.ORGANIZER)
        self.owner = _make_user('ticket_owner2', role=User.PARTICIPANT)
        self.event = _make_event(self.organizer)
        self.reg = Registration.objects.create(
            event=self.event, user=self.owner, status='confirmed'
        )
        self.ticket = Ticket.objects.get(registration=self.reg)
        self.client = Client()

    @unittest.skipUnless(HAS_QRCODE, "qrcode not installed in this environment")
    def test_qr_image_endpoint_returns_png_for_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse('tickets:ticket_qr', kwargs={'ticket_code': self.ticket.ticket_code})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    @unittest.skipUnless(HAS_QRCODE, "qrcode not installed in this environment")
    def test_qr_image_endpoint_denies_non_owner(self):
        stranger = _make_user('qr_stranger', role=User.PARTICIPANT)
        self.client.force_login(stranger)
        response = self.client.get(
            reverse('tickets:ticket_qr', kwargs={'ticket_code': self.ticket.ticket_code})
        )
        self.assertEqual(response.status_code, 403)

    @unittest.skipUnless(HAS_QRCODE and HAS_REPORTLAB, "qrcode/reportlab not installed in this environment")
    def test_ticket_pdf_endpoint_returns_pdf_for_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse('tickets:ticket_pdf', kwargs={'ticket_code': self.ticket.ticket_code})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))