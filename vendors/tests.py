from datetime import date

from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import VendorContract, VendorPayment, VendorProfile, VendorRating, VendorService


class VendorProfileModelTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(username='vuser', password='pw12345!', role=User.VENDOR)
        self.profile = VendorProfile.objects.create(
            user=self.vendor_user, company_name='Sparkle Catering', service_type='catering',
        )

    def test_slug_auto_generated(self):
        self.assertEqual(self.profile.slug, 'sparkle-catering')

    def test_default_status_is_pending(self):
        self.assertEqual(self.profile.status, 'pending')
        self.assertFalse(self.profile.is_approved)

    def test_performance_score_none_without_ratings(self):
        self.assertIsNone(self.profile.performance_score)

    def test_performance_score_averages_quality_and_delivery(self):
        admin = User.objects.create_user(username='vadmin', password='pw12345!', role=User.SUPER_ADMIN)
        VendorRating.objects.create(vendor=self.profile, rated_by=admin, service_quality=4, delivery_time=2)
        VendorRating.objects.create(vendor=self.profile, rated_by=admin, service_quality=5, delivery_time=3)
        # avg quality = 4.5, avg delivery = 2.5 -> performance = 3.5
        self.assertEqual(self.profile.avg_service_quality, 4.5)
        self.assertEqual(self.profile.avg_delivery_time, 2.5)
        self.assertEqual(self.profile.performance_score, 3.5)


class VendorContractPaymentTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(username='vuser2', password='pw12345!', role=User.VENDOR)
        self.profile = VendorProfile.objects.create(
            user=self.vendor_user, company_name='Bright Lights AV', service_type='sound_lighting', status='approved',
        )
        self.organizer = User.objects.create_user(username='vorg', password='pw12345!', role=User.ORGANIZER)
        self.contract = VendorContract.objects.create(
            vendor=self.profile, title='Wedding AV setup', amount=10000, created_by=self.organizer,
        )

    def test_balance_due_with_no_payments(self):
        self.assertEqual(self.contract.total_paid, 0)
        self.assertEqual(self.contract.balance_due, 10000)

    def test_balance_due_after_partial_payment(self):
        VendorPayment.objects.create(
            vendor=self.profile, contract=self.contract, amount=4000, status='paid',
            payment_date=date.today(), recorded_by=self.organizer,
        )
        self.assertEqual(self.contract.total_paid, 4000)
        self.assertEqual(self.contract.balance_due, 6000)

    def test_pending_payment_not_counted_toward_total_paid(self):
        VendorPayment.objects.create(
            vendor=self.profile, contract=self.contract, amount=4000, status='pending',
            payment_date=date.today(), recorded_by=self.organizer,
        )
        self.assertEqual(self.contract.total_paid, 0)

    def test_contract_end_date_before_start_date_rejected(self):
        with self.assertRaises(Exception):
            VendorContract.objects.create(
                vendor=self.profile, title='Bad dates', amount=100,
                start_date=date(2026, 6, 10), end_date=date(2026, 6, 1),
            )


class VendorPermissionViewTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(username='vuser3', password='pw12345!', role=User.VENDOR)
        self.profile = VendorProfile.objects.create(
            user=self.vendor_user, company_name='Golden Decor', service_type='decoration', status='pending',
        )
        self.staff = User.objects.create_user(username='vstaff', password='pw12345!', role=User.STAFF)
        self.organizer = User.objects.create_user(username='vorg2', password='pw12345!', role=User.ORGANIZER)
        self.participant = User.objects.create_user(username='vpart', password='pw12345!')

    def test_pending_vendor_hidden_from_public_list(self):
        response = self.client.get(reverse('vendors:vendor_list'))
        self.assertNotContains(response, 'Golden Decor')

    def test_pending_vendor_visible_to_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('vendors:vendor_list'))
        self.assertContains(response, 'Golden Decor')

    def test_pending_vendor_detail_blocked_for_public(self):
        response = self.client.get(reverse('vendors:vendor_detail', args=[self.profile.slug]))
        self.assertRedirects(response, reverse('vendors:vendor_list'))

    def test_owner_can_view_own_pending_profile(self):
        self.client.force_login(self.vendor_user)
        response = self.client.get(reverse('vendors:vendor_detail', args=[self.profile.slug]))
        self.assertEqual(response.status_code, 200)

    def test_staff_can_approve_vendor(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('vendors:vendor_approve', args=[self.profile.slug]))
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, 'approved')

    def test_organizer_cannot_approve_vendor(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('vendors:vendor_approve', args=[self.profile.slug]))
        self.assertRedirects(response, reverse('dashboard:dashboard'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, 'pending')

    def test_participant_cannot_create_contract(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('vendors:vendor_contract_create', args=[self.profile.slug]))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_can_create_contract(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('vendors:vendor_contract_create', args=[self.profile.slug]), {
            'title': 'Decor for launch event', 'description': '', 'amount': 5000,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VendorContract.objects.filter(vendor=self.profile).count(), 1)

    def test_non_owner_cannot_add_service(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('vendors:vendor_service_create', args=[self.profile.slug]), {
            'name': 'Balloon arch', 'description': '', 'price': 1500, 'price_unit': 'flat', 'is_active': 'on',
        })
        self.assertEqual(VendorService.objects.filter(vendor=self.profile).count(), 0)

    def test_owner_can_add_service(self):
        self.client.force_login(self.vendor_user)
        response = self.client.post(reverse('vendors:vendor_service_create', args=[self.profile.slug]), {
            'name': 'Balloon arch', 'description': '', 'price': 1500, 'price_unit': 'flat', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VendorService.objects.filter(vendor=self.profile).count(), 1)

    def test_non_vendor_role_cannot_self_register_profile(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('vendors:vendor_profile_create'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_cannot_update_another_organizers_contract_status(self):
        # Regression test for a gap closed during the RBAC upgrade: contract
        # status updates used to be role-gated only (any Organizer could
        # update ANY contract), not ownership-scoped.
        other_organizer = User.objects.create_user(username='vorg3', password='pw12345!', role=User.ORGANIZER)
        contract = VendorContract.objects.create(
            vendor=self.profile, title='Catering deal', amount=1000, created_by=self.organizer,
        )
        self.client.force_login(other_organizer)
        response = self.client.post(
            reverse('vendors:vendor_contract_update_status', args=[contract.pk]), {'status': 'signed'}
        )
        contract.refresh_from_db()
        self.assertNotEqual(contract.status, 'signed')

        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse('vendors:vendor_contract_update_status', args=[contract.pk]), {'status': 'signed'}
        )
        contract.refresh_from_db()
        self.assertEqual(contract.status, 'signed')
