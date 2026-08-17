from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from budget.models import EventBudget
from events.models import Event
from users.models import User
from .models import EventSponsorship, Sponsor


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


class SponsorModelTests(TestCase):
    def test_slug_auto_generated_and_unique(self):
        s1 = Sponsor.objects.create(company_name='Acme Corp')
        s2 = Sponsor.objects.create(company_name='Acme Corp')
        self.assertEqual(s1.slug, 'acme-corp')
        self.assertEqual(s2.slug, 'acme-corp-1')

    def test_total_confirmed_amount_only_counts_confirmed_and_paid(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        event = make_event(organizer)
        sponsor = Sponsor.objects.create(company_name='Acme Corp')

        EventSponsorship.objects.create(
            sponsor=sponsor, event=event, package='gold', amount=Decimal('5000'), status='pending'
        )
        EventSponsorship.objects.create(
            sponsor=sponsor, event=event, package='silver', amount=Decimal('2000'), status='confirmed'
        )
        EventSponsorship.objects.create(
            sponsor=sponsor, event=event, package='bronze', amount=Decimal('1000'), status='paid'
        )
        EventSponsorship.objects.create(
            sponsor=sponsor, event=event, package='custom', amount=Decimal('9999'), status='cancelled'
        )

        self.assertEqual(sponsor.total_confirmed_amount, Decimal('3000'))


class BudgetSponsorshipIntegrationTests(TestCase):
    """Confirms EventSponsorship correctly rolls up into EventBudget.total_revenue
    (Module 10 closing the loop on Module 6's deferred 'real Sponsor model' note),
    without disturbing the pre-existing manual RevenueEntry(source='sponsorship')
    path."""

    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.event = make_event(self.organizer)
        self.budget = EventBudget.objects.create(event=self.event, estimated_budget=Decimal('10000'))
        self.sponsor = Sponsor.objects.create(company_name='Acme Corp')

    def test_pending_sponsorship_does_not_count_toward_revenue(self):
        EventSponsorship.objects.create(
            sponsor=self.sponsor, event=self.event, package='gold',
            amount=Decimal('4000'), status='pending',
        )
        self.assertEqual(self.budget.sponsorship_deals_total, 0)
        self.assertEqual(self.budget.total_revenue, 0)

    def test_confirmed_and_paid_sponsorships_count_toward_revenue(self):
        EventSponsorship.objects.create(
            sponsor=self.sponsor, event=self.event, package='gold',
            amount=Decimal('4000'), status='confirmed',
        )
        EventSponsorship.objects.create(
            sponsor=self.sponsor, event=self.event, package='silver',
            amount=Decimal('1500'), status='paid',
        )
        self.assertEqual(self.budget.sponsorship_deals_total, Decimal('5500'))
        self.assertEqual(self.budget.total_revenue, Decimal('5500'))

    def test_legacy_manual_sponsorship_revenue_entry_still_counts_alongside(self):
        from budget.models import RevenueEntry
        RevenueEntry.objects.create(
            budget=self.budget, source='sponsorship', sponsor_name='Legacy Sponsor Inc',
            amount=Decimal('1000'), date=timezone.now().date(),
        )
        EventSponsorship.objects.create(
            sponsor=self.sponsor, event=self.event, package='gold',
            amount=Decimal('4000'), status='paid',
        )
        # Both the old free-text path and the new real Sponsor-linked path
        # count, and neither double-counts the other.
        self.assertEqual(self.budget.total_revenue, Decimal('5000'))

    def test_cancelled_sponsorship_does_not_count(self):
        EventSponsorship.objects.create(
            sponsor=self.sponsor, event=self.event, package='gold',
            amount=Decimal('4000'), status='cancelled',
        )
        self.assertEqual(self.budget.total_revenue, 0)


class SponsorPermissionTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(
            username='admin1', password='pw12345!', role=User.SUPER_ADMIN
        )
        self.organizer = User.objects.create_user(
            username='org1', password='pw12345!', role=User.ORGANIZER
        )
        self.other_organizer = User.objects.create_user(
            username='org2', password='pw12345!', role=User.ORGANIZER
        )
        self.staff = User.objects.create_user(
            username='staff1', password='pw12345!', role=User.STAFF
        )
        self.participant = User.objects.create_user(
            username='part1', password='pw12345!', role=User.PARTICIPANT
        )
        self.event = make_event(self.organizer)
        self.sponsor = Sponsor.objects.create(company_name='Acme Corp')

    def test_organizer_can_create_own_sponsor_but_not_edit_others(self):
        # Sponsor catalog management now follows the same
        # created_by-ownership pattern as Venue/Category/Resource:
        # Organizer can create and manage their own sponsors, but not
        # another Organizer's.
        self.client.login(username='org1', password='pw12345!')
        response = self.client.post(reverse('sponsors:sponsor_create'), {
            'company_name': 'Org1 Co', 'website': '', 'contact_person': '',
            'email': '', 'phone_number': '', 'description': '', 'is_active': True,
        })
        self.assertTrue(Sponsor.objects.filter(company_name='Org1 Co').exists())
        own_sponsor = Sponsor.objects.get(company_name='Org1 Co')
        self.assertEqual(own_sponsor.created_by, self.organizer)

        self.client.login(username='org2', password='pw12345!')
        response = self.client.get(reverse('sponsors:sponsor_edit', args=[own_sponsor.slug]))
        self.assertRedirects(response, reverse('sponsors:sponsor_detail', args=[own_sponsor.slug]))

        self.client.login(username='part1', password='pw12345!')
        response = self.client.post(reverse('sponsors:sponsor_create'), {
            'company_name': 'Blocked Co', 'website': '', 'contact_person': '',
            'email': '', 'phone_number': '', 'description': '', 'is_active': True,
        })
        self.assertFalse(Sponsor.objects.filter(company_name='Blocked Co').exists())

        self.client.login(username='admin1', password='pw12345!')
        response = self.client.post(reverse('sponsors:sponsor_create'), {
            'company_name': 'Allowed Co', 'website': '', 'contact_person': '',
            'email': '', 'phone_number': '', 'description': '', 'is_active': True,
        })
        self.assertTrue(Sponsor.objects.filter(company_name='Allowed Co').exists())

    def test_participant_cannot_browse_catalog(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('sponsors:sponsor_list'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_can_create_sponsorship_for_own_event_only(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.post(
            reverse('sponsors:event_sponsorship_create', kwargs={'event_slug': self.event.slug}),
            {'sponsor': self.sponsor.pk, 'package': 'gold', 'amount': '5000', 'benefits': '', 'notes': ''}
        )
        self.assertTrue(EventSponsorship.objects.filter(event=self.event, sponsor=self.sponsor).exists())
        deal = EventSponsorship.objects.get(event=self.event, sponsor=self.sponsor)
        self.assertEqual(deal.status, 'pending')

        self.client.login(username='org2', password='pw12345!')
        response = self.client.post(
            reverse('sponsors:event_sponsorship_create', kwargs={'event_slug': self.event.slug}),
            {'sponsor': self.sponsor.pk, 'package': 'silver', 'amount': '2000', 'benefits': '', 'notes': ''}
        )
        self.assertEqual(
            EventSponsorship.objects.filter(event=self.event, package='silver').count(), 0
        )

    def test_deal_status_change_scoped_to_event_organizer_staff_or_admin(self):
        deal = EventSponsorship.objects.create(
            sponsor=self.sponsor, event=self.event, package='gold',
            amount=Decimal('5000'), status='pending',
        )
        # org2 doesn't organize self.event — blocked.
        self.client.login(username='org2', password='pw12345!')
        self.client.post(
            reverse('sponsors:event_sponsorship_status_update', kwargs={'pk': deal.pk}),
            {'status': 'paid'}
        )
        deal.refresh_from_db()
        self.assertEqual(deal.status, 'pending')

        # org1 organizes self.event (see make_event(self.organizer) in
        # setUp) — allowed, same as Budget's per-event ownership pattern.
        self.client.login(username='org1', password='pw12345!')
        self.client.post(
            reverse('sponsors:event_sponsorship_status_update', kwargs={'pk': deal.pk}),
            {'status': 'confirmed'}
        )
        deal.refresh_from_db()
        self.assertEqual(deal.status, 'confirmed')

        self.client.login(username='staff1', password='pw12345!')
        response = self.client.post(
            reverse('sponsors:event_sponsorship_status_update', kwargs={'pk': deal.pk}),
            {'status': 'paid'}
        )
        deal.refresh_from_db()
        self.assertEqual(deal.status, 'paid')
