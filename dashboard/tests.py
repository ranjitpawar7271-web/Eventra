from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from budget.models import EventBudget, Expense, RevenueEntry
from events.models import Event
from sponsors.models import EventSponsorship, Sponsor
from users.models import User
from vendors.models import VendorContract, VendorPayment, VendorProfile


def make_event(organizer, title='Test Event'):
    now = timezone.now()
    return Event.objects.create(
        title=title,
        description='A test event.',
        organizer=organizer,
        location='Community Hall',
        start_date=now + timedelta(days=10),
        end_date=now + timedelta(days=10, hours=3),
        capacity=100,
        price=0,
    )


class SuperAdminDashboardFinancialsTests(TestCase):
    """Covers the Super Admin system-wide panel in dashboard/views.py,
    specifically that sys_total_revenue / sys_net_profit correctly roll up
    manual RevenueEntry rows, confirmed EventSponsorship deals (Module 10),
    direct Expenses, and paid VendorPayments -- all in one number, matching
    what EventBudget.total_revenue/total_expenses compute per-event.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            username='admin1', password='pw12345!', role=User.SUPER_ADMIN
        )
        self.organizer = User.objects.create_user(
            username='org1', password='pw12345!', role=User.ORGANIZER
        )
        self.event = make_event(self.organizer)
        self.budget = EventBudget.objects.create(event=self.event, estimated_budget=Decimal('10000'))

    def _get_dashboard(self):
        self.client.login(username='admin1', password='pw12345!')
        return self.client.get(reverse('dashboard:dashboard'))

    def test_zero_state(self):
        response = self._get_dashboard()
        self.assertEqual(response.context['sys_total_revenue'], 0)
        self.assertEqual(response.context['sys_total_expenses'], 0)
        self.assertEqual(response.context['sys_net_profit'], 0)

    def test_manual_revenue_entry_counts(self):
        RevenueEntry.objects.create(
            budget=self.budget, source='ticket_sales', amount=Decimal('3000'), date=date.today(),
        )
        response = self._get_dashboard()
        self.assertEqual(response.context['sys_manual_revenue'], Decimal('3000'))
        self.assertEqual(response.context['sys_total_revenue'], Decimal('3000'))

    def test_confirmed_sponsorship_counts_toward_system_revenue(self):
        sponsor = Sponsor.objects.create(company_name='Acme Corp')
        EventSponsorship.objects.create(
            sponsor=sponsor, event=self.event, package='gold',
            amount=Decimal('5000'), status='confirmed',
        )
        # A pending one should NOT count.
        EventSponsorship.objects.create(
            sponsor=sponsor, event=self.event, package='silver',
            amount=Decimal('1200'), status='pending',
        )
        response = self._get_dashboard()
        self.assertEqual(response.context['sys_sponsorship_revenue'], Decimal('5000'))
        self.assertEqual(response.context['sys_total_revenue'], Decimal('5000'))

    def test_manual_revenue_and_sponsorship_combine_without_double_counting(self):
        RevenueEntry.objects.create(
            budget=self.budget, source='sponsorship', sponsor_name='Legacy Sponsor',
            amount=Decimal('1000'), date=date.today(),
        )
        sponsor = Sponsor.objects.create(company_name='Acme Corp')
        EventSponsorship.objects.create(
            sponsor=sponsor, event=self.event, package='gold',
            amount=Decimal('4000'), status='paid',
        )
        response = self._get_dashboard()
        self.assertEqual(response.context['sys_manual_revenue'], Decimal('1000'))
        self.assertEqual(response.context['sys_sponsorship_revenue'], Decimal('4000'))
        self.assertEqual(response.context['sys_total_revenue'], Decimal('5000'))

    def test_net_profit_combines_all_revenue_and_expense_sources(self):
        # Revenue: manual + sponsorship
        RevenueEntry.objects.create(
            budget=self.budget, source='ticket_sales', amount=Decimal('2000'), date=date.today(),
        )
        sponsor = Sponsor.objects.create(company_name='Acme Corp')
        EventSponsorship.objects.create(
            sponsor=sponsor, event=self.event, package='gold',
            amount=Decimal('3000'), status='paid',
        )
        # Expenses: direct + vendor payment
        Expense.objects.create(
            budget=self.budget, category='venue', description='Hall rent',
            amount=Decimal('1500'), date=date.today(), status='paid',
        )
        vendor_user = User.objects.create_user(username='vend1', password='pw12345!', role=User.VENDOR)
        vendor = VendorProfile.objects.create(user=vendor_user, company_name='Catering Co')
        contract = VendorContract.objects.create(
            vendor=vendor, event=self.event, title='Catering deal',
            amount=Decimal('2000'), start_date=date.today(), end_date=date.today() + timedelta(days=1),
        )
        VendorPayment.objects.create(
            vendor=vendor, contract=contract, amount=Decimal('800'), status='paid', payment_date=date.today()
        )

        response = self._get_dashboard()
        self.assertEqual(response.context['sys_total_revenue'], Decimal('5000'))   # 2000 + 3000
        self.assertEqual(response.context['sys_total_expenses'], Decimal('2300'))  # 1500 + 800
        self.assertEqual(response.context['sys_net_profit'], Decimal('2700'))

    def test_non_admin_does_not_get_system_wide_context(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('dashboard:dashboard'))
        self.assertNotIn('sys_total_revenue', response.context)


class ActivityFeedTests(TestCase):
    """Covers dashboard.views.activity_feed — Module 10's 'Activity Feed',
    built as a read-only aggregation over existing timestamped records
    rather than a new logging system (see the view's docstring)."""

    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)

    def test_requires_login(self):
        response = self.client.get(reverse('dashboard:activity_feed'))
        self.assertNotEqual(response.status_code, 200)

    def test_empty_state(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('dashboard:activity_feed'))
        self.assertEqual(response.context['entries'], [])

    def test_registration_appears_in_feed(self):
        from events.models import Registration
        Registration.objects.create(event=self.event, user=self.participant, status='confirmed')
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('dashboard:activity_feed'))
        texts = [e['text'] for e in response.context['entries']]
        self.assertTrue(any(self.event.title in t for t in texts))

    def test_wishlist_addition_appears_in_feed(self):
        from wishlist.models import FavoriteEvent
        FavoriteEvent.objects.create(user=self.participant, event=self.event)
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('dashboard:activity_feed'))
        self.assertEqual(len(response.context['entries']), 1)
        self.assertIn('wishlist', response.context['entries'][0]['text'])

    def test_feed_only_shows_own_activity(self):
        from wishlist.models import FavoriteEvent
        other = User.objects.create_user(username='other1', password='pw12345!', role=User.PARTICIPANT)
        FavoriteEvent.objects.create(user=other, event=self.event)

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('dashboard:activity_feed'))
        self.assertEqual(response.context['entries'], [])

    def test_organizer_event_creation_appears_for_organizer_only(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('dashboard:activity_feed'))
        texts = [e['text'] for e in response.context['entries']]
        self.assertTrue(any('You created' in t for t in texts))

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('dashboard:activity_feed'))
        texts = [e['text'] for e in response.context['entries']]
        self.assertFalse(any('You created' in t for t in texts))