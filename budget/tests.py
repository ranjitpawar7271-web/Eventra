from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from users.models import User
from vendors.models import VendorContract, VendorPayment, VendorProfile
from .models import EventBudget, Expense, RevenueEntry


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


class EventBudgetMathTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.event = make_event(self.organizer)
        self.budget = EventBudget.objects.create(event=self.event, estimated_budget=Decimal('10000'))

    def test_zero_totals_with_no_rows(self):
        self.assertEqual(self.budget.total_expenses, 0)
        self.assertEqual(self.budget.total_revenue, 0)
        self.assertEqual(self.budget.profit_or_loss, 0)
        self.assertEqual(self.budget.variance, Decimal('10000'))

    def test_pending_expense_does_not_count_toward_actuals(self):
        Expense.objects.create(
            budget=self.budget, category='venue', description='Hall rent',
            amount=Decimal('2000'), date=date.today(), status='pending',
        )
        self.assertEqual(self.budget.total_expenses, 0)
        self.assertEqual(self.budget.variance, Decimal('10000'))

    def test_approved_and_paid_expenses_count(self):
        Expense.objects.create(
            budget=self.budget, category='venue', description='Hall rent',
            amount=Decimal('2000'), date=date.today(), status='approved',
        )
        Expense.objects.create(
            budget=self.budget, category='catering', description='Snacks',
            amount=Decimal('1500'), date=date.today(), status='paid',
        )
        Expense.objects.create(
            budget=self.budget, category='marketing', description='Flyers',
            amount=Decimal('500'), date=date.today(), status='pending',
        )
        self.assertEqual(self.budget.total_expenses, Decimal('3500'))
        self.assertEqual(self.budget.variance, Decimal('6500'))
        self.assertFalse(self.budget.is_over_budget)

    def test_over_budget_flag(self):
        Expense.objects.create(
            budget=self.budget, category='venue', description='Hall rent',
            amount=Decimal('12000'), date=date.today(), status='paid',
        )
        self.assertTrue(self.budget.is_over_budget)
        self.assertEqual(self.budget.variance, Decimal('-2000'))
        self.assertEqual(self.budget.variance_abs, Decimal('2000'))

    def test_revenue_totals_and_profit_loss(self):
        RevenueEntry.objects.create(
            budget=self.budget, source='ticket_sales', amount=Decimal('5000'), date=date.today(),
        )
        RevenueEntry.objects.create(
            budget=self.budget, source='sponsorship', sponsor_name='Acme Co',
            amount=Decimal('3000'), date=date.today(),
        )
        Expense.objects.create(
            budget=self.budget, category='catering', description='Snacks',
            amount=Decimal('1500'), date=date.today(), status='paid',
        )
        self.assertEqual(self.budget.total_revenue, Decimal('8000'))
        self.assertEqual(self.budget.profit_or_loss, Decimal('6500'))
        self.assertTrue(self.budget.is_profitable)

    def test_sponsorship_requires_sponsor_name(self):
        with self.assertRaises(Exception):
            RevenueEntry.objects.create(
                budget=self.budget, source='sponsorship', amount=Decimal('1000'), date=date.today(),
            )

    def test_vendor_payment_reused_as_expense_input(self):
        vendor_user = User.objects.create_user(username='vend1', password='pw12345!', role=User.VENDOR)
        vendor = VendorProfile.objects.create(user=vendor_user, company_name='Acme Catering')
        contract = VendorContract.objects.create(
            vendor=vendor, event=self.event, title='Catering deal', amount=Decimal('4000'),
        )
        VendorPayment.objects.create(
            vendor=vendor, contract=contract, amount=Decimal('4000'),
            status='paid', payment_date=date.today(),
        )
        # A pending payment (different contract) should NOT count.
        contract2 = VendorContract.objects.create(
            vendor=vendor, event=self.event, title='Extra deal', amount=Decimal('1000'),
        )
        VendorPayment.objects.create(
            vendor=vendor, contract=contract2, amount=Decimal('1000'),
            status='pending', payment_date=date.today(),
        )
        self.assertEqual(self.budget.vendor_payments_total, Decimal('4000'))
        self.assertEqual(self.budget.total_expenses, Decimal('4000'))

    def test_category_breakdown_includes_only_confirmed_and_all_categories(self):
        Expense.objects.create(
            budget=self.budget, category='venue', description='Hall',
            amount=Decimal('1000'), date=date.today(), status='approved',
        )
        Expense.objects.create(
            budget=self.budget, category='venue', description='Deposit',
            amount=Decimal('500'), date=date.today(), status='pending',
        )
        breakdown = {row['code']: row['total'] for row in self.budget.category_breakdown}
        self.assertEqual(breakdown['venue'], Decimal('1000'))
        self.assertEqual(breakdown['catering'], 0)
        self.assertIn('miscellaneous', breakdown)


class BudgetPermissionTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org2', password='pw12345!', role=User.ORGANIZER)
        self.other_organizer = User.objects.create_user(username='org3', password='pw12345!', role=User.ORGANIZER)
        self.staff = User.objects.create_user(username='staffuser', password='pw12345!', role=User.STAFF)
        self.participant = User.objects.create_user(username='partuser', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)

    def test_organizer_can_set_up_own_budget(self):
        self.client.login(username='org2', password='pw12345!')
        response = self.client.post(
            reverse('budget:budget_setup', kwargs={'event_slug': self.event.slug}),
            {'estimated_budget': '5000'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventBudget.objects.filter(event=self.event).exists())

    def test_other_organizer_cannot_set_up_someone_elses_budget(self):
        self.client.login(username='org3', password='pw12345!')
        response = self.client.post(
            reverse('budget:budget_setup', kwargs={'event_slug': self.event.slug}),
            {'estimated_budget': '5000'},
        )
        self.assertFalse(EventBudget.objects.filter(event=self.event).exists())

    def test_participant_cannot_view_budget_list(self):
        self.client.login(username='partuser', password='pw12345!')
        response = self.client.get(reverse('budget:budget_list'))
        self.assertEqual(response.status_code, 302)

    def test_staff_can_manage_any_events_budget(self):
        self.client.login(username='staffuser', password='pw12345!')
        response = self.client.post(
            reverse('budget:budget_setup', kwargs={'event_slug': self.event.slug}),
            {'estimated_budget': '7500'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventBudget.objects.filter(event=self.event).exists())

    def test_expense_pending_by_default_not_visible_in_actuals_until_confirmed(self):
        self.client.login(username='org2', password='pw12345!')
        budget = EventBudget.objects.create(event=self.event, estimated_budget=Decimal('1000'))
        self.client.post(
            reverse('budget:expense_create', kwargs={'event_slug': self.event.slug}),
            {'category': 'catering', 'description': 'Snacks', 'amount': '300', 'date': date.today(), 'status': 'pending'},
        )
        budget.refresh_from_db()
        expense = budget.expenses.first()
        self.assertIsNotNone(expense)
        self.assertEqual(expense.status, 'pending')
        self.assertEqual(budget.total_expenses, 0)

        self.client.post(reverse('budget:expense_status_update', kwargs={'pk': expense.pk}), {'status': 'paid'})
        expense.refresh_from_db()
        self.assertEqual(expense.status, 'paid')
        self.assertEqual(budget.total_expenses, Decimal('300'))
