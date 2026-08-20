"""
Coverage for the payments app, focused on the capacity-safety fix in
`payments/services.py::process_mock_payment`.

Background bug this guards against: `Registration.status == 'pending_payment'`
does NOT reserve a seat (see `Event.seats_taken`, which only counts
'confirmed' registrations). That's fine by itself — it's how the project
lets more people start checkout than there are seats, routing the losers to
the waitlist. But the previous `process_mock_payment` confirmed a
registration purely because ITS OWN payment succeeded, with no re-check of
whether a seat was still actually available at that moment. Two pending
registrations for a capacity-1 event could therefore both end up
'confirmed' if their payments completed close together — exceeding
capacity.

The fix re-checks capacity (and event/registration lifecycle) under a
select_for_update() lock on the Event row immediately before confirming,
inside the same atomic transaction as marking the payment successful.

Run with:
    python manage.py test payments
"""
import threading
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from categories.models import Category
from events.models import Event, Registration, WaitlistEntry
from tickets.models import Ticket
from workflow.models import Notification
from . import services
from .models import Payment

User = get_user_model()


def _make_user(username, role=User.PARTICIPANT, **kwargs):
    return User.objects.create_user(
        username=username, password='pass1234', role=role,
        email=f'{username}@example.com', **kwargs
    )


def _make_paid_event(organizer, capacity=1, price=100, **kwargs):
    category = Category.objects.create(name=f'Cat-{uuid.uuid4().hex[:10]}')
    defaults = dict(
        title=f"Paid Event {uuid.uuid4().hex[:6]}",
        description='desc',
        organizer=organizer,
        category=category,
        location='Test Hall',
        start_date=timezone.now() + timedelta(days=5),
        end_date=timezone.now() + timedelta(days=5, hours=2),
        capacity=capacity,
        price=price,
        status='published',
    )
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


def _pending_payment(event, user):
    """Mirror events.views.event_register's paid-event branch: a
    pending_payment Registration plus its pending Payment."""
    registration = Registration.objects.create(event=event, user=user, status='pending_payment')
    payment = services.get_or_create_pending_payment(registration)
    return registration, payment


class CapacitySafePaymentConfirmationTests(TestCase):
    """Tests 1-4 from the task list: the core over-booking scenario and
    its building blocks."""

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.user_a = _make_user('user_a')
        self.user_b = _make_user('user_b')

    # 1. capacity 1 + one confirmed registration -------------------------
    def test_capacity_one_first_payment_confirms(self):
        event = _make_paid_event(self.organizer, capacity=1)
        registration, payment = _pending_payment(event, self.user_a)

        result = services.process_mock_payment(payment, Payment.METHOD_CARD)

        self.assertTrue(result.is_successful)
        registration.refresh_from_db()
        self.assertEqual(registration.status, 'confirmed')
        self.assertEqual(event.seats_taken, 1)
        self.assertTrue(event.is_full)

    # 2. second registration ---------------------------------------------
    def test_second_pending_registration_allowed_before_payment(self):
        # Pending registrations don't reserve capacity, so a second user
        # can still start checkout even though the first has confirmed —
        # this is expected/by-design, not the bug.
        event = _make_paid_event(self.organizer, capacity=1)
        reg_a, pay_a = _pending_payment(event, self.user_a)
        services.process_mock_payment(pay_a, Payment.METHOD_CARD)

        reg_b, pay_b = _pending_payment(event, self.user_b)
        self.assertEqual(reg_b.status, 'pending_payment')
        self.assertEqual(pay_b.status, Payment.STATUS_PENDING)

    # 3. pending payment followed by another confirmed registration ------
    def test_stale_pending_payment_cannot_overbook_after_seat_taken(self):
        """The exact bug report scenario: User A goes pending first but
        pays last; User B pays first and takes the only seat. User A's
        late payment confirmation must NOT also confirm."""
        event = _make_paid_event(self.organizer, capacity=1)
        reg_a, pay_a = _pending_payment(event, self.user_a)   # A pending first
        reg_b, pay_b = _pending_payment(event, self.user_b)

        # B pays and confirms first, taking the only seat.
        services.process_mock_payment(pay_b, Payment.METHOD_CARD)
        reg_b.refresh_from_db()
        self.assertEqual(reg_b.status, 'confirmed')

        # A completes payment afterwards.
        result_a = services.process_mock_payment(pay_a, Payment.METHOD_UPI)

        reg_a.refresh_from_db()
        self.assertFalse(result_a.is_successful)
        self.assertEqual(result_a.status, Payment.STATUS_FAILED)
        self.assertEqual(reg_a.status, 'cancelled')

        # Capacity must never exceed 1 confirmed registration.
        self.assertEqual(
            Registration.objects.filter(event=event, status='confirmed').count(), 1
        )
        # A was routed to the waitlist instead of being silently dropped.
        self.assertTrue(
            WaitlistEntry.objects.filter(event=event, user=self.user_a, status=WaitlistEntry.STATUS_WAITING).exists()
        )

    # 4. payment confirmation when event becomes full --------------------
    def test_payment_confirmation_rechecks_capacity_not_just_own_status(self):
        event = _make_paid_event(self.organizer, capacity=2)
        reg_a, pay_a = _pending_payment(event, self.user_a)
        reg_b, pay_b = _pending_payment(event, self.user_b)
        user_c = _make_user('user_c')
        reg_c, pay_c = _pending_payment(event, user_c)

        services.process_mock_payment(pay_a, Payment.METHOD_CARD)
        services.process_mock_payment(pay_b, Payment.METHOD_CARD)
        # Event is now full (2/2). C's payment must fail even though C's
        # own payment record was perfectly valid — this proves the check
        # is against *current* capacity, not just "is my own payment ok".
        result_c = services.process_mock_payment(pay_c, Payment.METHOD_CARD)

        self.assertEqual(result_c.status, Payment.STATUS_FAILED)
        self.assertEqual(Registration.objects.filter(event=event, status='confirmed').count(), 2)

    # Duplicate confirmation: re-processing an already-successful payment
    # must be a safe no-op, not a double charge/double ticket.
    def test_already_successful_payment_is_not_reprocessed(self):
        event = _make_paid_event(self.organizer, capacity=5)
        registration, payment = _pending_payment(event, self.user_a)
        services.process_mock_payment(payment, Payment.METHOD_CARD)
        ticket_count_before = Ticket.objects.filter(registration=registration).count()

        # Call again with a different method — should be ignored.
        result = services.process_mock_payment(payment, Payment.METHOD_UPI)

        self.assertEqual(result.payment_method, Payment.METHOD_CARD)
        self.assertEqual(Ticket.objects.filter(registration=registration).count(), ticket_count_before)


class SimultaneousConfirmationTests(TransactionTestCase):
    """5. Two simultaneous confirmation attempts for the last seat.

    Uses real threads + TransactionTestCase (separate DB connections, real
    commits) so select_for_update() actually serializes the two requests,
    the way it would under a real webserver with concurrent requests.
    Requires a DB backend that supports row locking (sqlite3 in Django
    test mode falls back to whole-database locking, which still proves
    the property under test: at most one of the two confirms).
    """

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.user_a = _make_user('user_a')
        self.user_b = _make_user('user_b')

    def test_only_one_of_two_concurrent_payments_wins_last_seat(self):
        event = _make_paid_event(self.organizer, capacity=1)
        reg_a, pay_a = _pending_payment(event, self.user_a)
        reg_b, pay_b = _pending_payment(event, self.user_b)

        results = {}
        barrier = threading.Barrier(2)

        def run(payment, key):
            barrier.wait(timeout=5)
            try:
                result = services.process_mock_payment(payment, Payment.METHOD_CARD)
                results[key] = result.status
            except Exception:
                # SQLite (used in tests) doesn't give true row-level locks
                # the way Postgres/MySQL do in production — under heavy
                # contention a second writer can be rejected outright
                # instead of queuing behind select_for_update(). Either
                # way it must NOT end up as a successful confirmation past
                # capacity, which is the invariant asserted below.
                results[key] = 'errored'
            finally:
                connections.close_all()

        t1 = threading.Thread(target=run, args=(pay_a, 'a'))
        t2 = threading.Thread(target=run, args=(pay_b, 'b'))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # The invariant that actually matters: capacity is never exceeded,
        # no matter how the losing request's transaction resolved.
        confirmed_count = Registration.objects.filter(event=event, status='confirmed').count()
        self.assertEqual(confirmed_count, 1, "capacity was exceeded by concurrent confirmations")
        statuses = list(results.values())
        self.assertEqual(statuses.count(Payment.STATUS_SUCCESSFUL), 1)
        self.assertNotIn('successful', [s for s in statuses if s != Payment.STATUS_SUCCESSFUL])


class MockPaymentOutcomeTests(TestCase):
    """6-7. Straightforward successful/failed payment flows."""

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.user = _make_user('participant1')

    # 6. successful payment ----------------------------------------------
    def test_successful_payment_confirms_registration_and_marks_payment(self):
        event = _make_paid_event(self.organizer, capacity=10, price=250)
        registration, payment = _pending_payment(event, self.user)

        result = services.process_mock_payment(payment, Payment.METHOD_UPI)

        self.assertEqual(result.status, Payment.STATUS_SUCCESSFUL)
        self.assertEqual(result.payment_method, Payment.METHOD_UPI)
        self.assertIsNotNone(result.payment_date)
        registration.refresh_from_db()
        self.assertEqual(registration.status, 'confirmed')

    # 7. failed payment ----------------------------------------------------
    def test_simulated_failure_leaves_registration_pending_for_retry(self):
        event = _make_paid_event(self.organizer, capacity=10)
        registration, payment = _pending_payment(event, self.user)

        result = services.process_mock_payment(payment, Payment.METHOD_CARD, simulate_failure=True)

        self.assertEqual(result.status, Payment.STATUS_FAILED)
        self.assertTrue(result.failure_reason)
        registration.refresh_from_db()
        self.assertEqual(registration.status, 'pending_payment')
        self.assertFalse(Ticket.objects.filter(registration=registration).exists())

        # User can retry: a fresh call still works.
        retry = services.process_mock_payment(payment, Payment.METHOD_CARD)
        # `payment` is already resolved (failed), so this exact Payment
        # object won't flip to successful — a real retry mints a new
        # pending Payment via get_or_create_pending_payment, matching the
        # checkout view's flow.
        self.assertEqual(retry.status, Payment.STATUS_FAILED)
        new_payment = services.get_or_create_pending_payment(registration)
        self.assertNotEqual(new_payment.pk, payment.pk)
        retry2 = services.process_mock_payment(new_payment, Payment.METHOD_CARD)
        self.assertEqual(retry2.status, Payment.STATUS_SUCCESSFUL)


class RefundBehaviorTests(TestCase):
    """8. Refund cancels the registration/ticket and frees the seat."""

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.user_a = _make_user('user_a')
        self.user_b = _make_user('user_b')

    def test_refund_cancels_registration_and_ticket_and_promotes_waitlist(self):
        event = _make_paid_event(self.organizer, capacity=1)
        reg_a, pay_a = _pending_payment(event, self.user_a)
        pay_a = services.process_mock_payment(pay_a, Payment.METHOD_CARD)
        ticket = Ticket.objects.get(registration=reg_a)
        self.assertEqual(ticket.status, Ticket.STATUS_ISSUED)

        # Event is full; B joins the waitlist.
        from events import waitlist_services
        entry, created = waitlist_services.join_waitlist(event, self.user_b)
        self.assertTrue(created)

        refunded = services.refund_payment(pay_a)

        self.assertTrue(refunded)
        pay_a.refresh_from_db()
        self.assertEqual(pay_a.status, Payment.STATUS_REFUNDED)
        self.assertEqual(pay_a.refund_amount, pay_a.amount)

        reg_a.refresh_from_db()
        self.assertEqual(reg_a.status, 'cancelled')
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.STATUS_CANCELLED)

        # The freed seat was offered to the next waitlisted user.
        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.STATUS_NOTIFIED)

    def test_refund_only_allowed_on_successful_payment(self):
        event = _make_paid_event(self.organizer, capacity=5)
        registration, payment = _pending_payment(event, self.user_a)  # still pending
        self.assertFalse(services.refund_payment(payment))


class TicketAndNotificationGenerationTests(TestCase):
    """9-10. Ticket + notification side effects of the payment flow."""

    def setUp(self):
        self.organizer = _make_user('organizer1', role=User.ORGANIZER)
        self.user = _make_user('participant1')

    # 9. ticket generation --------------------------------------------------
    def test_ticket_generated_on_successful_payment(self):
        event = _make_paid_event(self.organizer, capacity=5, price=99)
        registration, payment = _pending_payment(event, self.user)

        services.process_mock_payment(payment, Payment.METHOD_WALLET)

        ticket = Ticket.objects.get(registration=registration)
        self.assertEqual(ticket.status, Ticket.STATUS_ISSUED)
        self.assertEqual(ticket.ticket_type, Ticket.TYPE_PAID)
        self.assertTrue(ticket.ticket_code)
        self.assertTrue(ticket.qr_token)

    def test_no_ticket_generated_when_capacity_lost_during_payment(self):
        event = _make_paid_event(self.organizer, capacity=1)
        reg_a, pay_a = _pending_payment(event, self.user)
        other = _make_user('other_user')
        reg_b, pay_b = _pending_payment(event, other)

        services.process_mock_payment(pay_b, Payment.METHOD_CARD)  # takes the seat
        services.process_mock_payment(pay_a, Payment.METHOD_CARD)  # loses the race

        self.assertFalse(Ticket.objects.filter(registration=reg_a).exists())

    # 10. notification generation -------------------------------------------
    def test_notifications_for_success_failure_and_capacity_loss(self):
        organizer = self.organizer
        event = _make_paid_event(organizer, capacity=1)
        winner = self.user
        loser = _make_user('loser_user')

        reg_winner, pay_winner = _pending_payment(event, winner)
        reg_loser, pay_loser = _pending_payment(event, loser)

        services.process_mock_payment(pay_winner, Payment.METHOD_CARD)
        self.assertTrue(
            Notification.objects.filter(user=winner, notification_type=Notification.TYPE_PAYMENT).exists()
        )

        services.process_mock_payment(pay_loser, Payment.METHOD_CARD)
        self.assertTrue(
            Notification.objects.filter(user=loser, notification_type=Notification.TYPE_CAPACITY).exists()
        )

        failer = _make_user('failer_user')
        event2 = _make_paid_event(organizer, capacity=5)
        reg_fail, pay_fail = _pending_payment(event2, failer)
        services.process_mock_payment(pay_fail, Payment.METHOD_CARD, simulate_failure=True)
        self.assertTrue(
            Notification.objects.filter(user=failer, notification_type=Notification.TYPE_PAYMENT).exists()
        )

    def test_refund_generates_notification(self):
        event = _make_paid_event(self.organizer, capacity=5)
        registration, payment = _pending_payment(event, self.user)
        payment = services.process_mock_payment(payment, Payment.METHOD_CARD)
        Notification.objects.filter(user=self.user).delete()

        services.refund_payment(payment)

        self.assertTrue(
            Notification.objects.filter(user=self.user, notification_type=Notification.TYPE_PAYMENT).exists()
        )