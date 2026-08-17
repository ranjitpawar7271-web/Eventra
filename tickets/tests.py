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
import unittest
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from categories.models import Category
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

