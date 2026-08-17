from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User
from .models import DamageReport, Resource, ResourceAllocation

_BASE_TIME = timezone.now()


def dt(hours_from_base):
    return _BASE_TIME + timedelta(hours=hours_from_base)


class ResourceModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='radmin', password='pw12345!', role=User.SUPER_ADMIN)
        self.resource = Resource.objects.create(
            name='Plastic Chair', category='chairs', total_quantity=100, unit='pcs', created_by=self.admin,
        )

    def test_slug_auto_generated(self):
        self.assertEqual(self.resource.slug, 'plastic-chair')

    def test_full_pool_available_with_no_allocations(self):
        self.assertEqual(self.resource.available_quantity(dt(1), dt(2)), 100)

    def test_allocation_reduces_availability(self):
        ResourceAllocation.objects.create(
            resource=self.resource, quantity=40, requested_by=self.admin,
            start_datetime=dt(1), end_datetime=dt(3), status='allocated',
        )
        self.assertEqual(self.resource.available_quantity(dt(2), dt(4)), 60)
        # Non-overlapping window: full pool still available.
        self.assertEqual(self.resource.available_quantity(dt(5), dt(6)), 100)

    def test_double_allocation_beyond_pool_is_rejected(self):
        ResourceAllocation.objects.create(
            resource=self.resource, quantity=70, requested_by=self.admin,
            start_datetime=dt(1), end_datetime=dt(3), status='allocated',
        )
        with self.assertRaises(Exception):
            ResourceAllocation.objects.create(
                resource=self.resource, quantity=40, requested_by=self.admin,
                start_datetime=dt(2), end_datetime=dt(4), status='allocated',
            )

    def test_multiple_allocations_within_pool_succeed(self):
        ResourceAllocation.objects.create(
            resource=self.resource, quantity=30, requested_by=self.admin,
            start_datetime=dt(1), end_datetime=dt(3), status='allocated',
        )
        ResourceAllocation.objects.create(
            resource=self.resource, quantity=30, requested_by=self.admin,
            start_datetime=dt(2), end_datetime=dt(4), status='allocated',
        )
        self.assertEqual(ResourceAllocation.objects.count(), 2)
        self.assertEqual(self.resource.available_quantity(dt(2), dt(3)), 40)

    def test_cancelled_allocation_frees_up_pool(self):
        allocation = ResourceAllocation.objects.create(
            resource=self.resource, quantity=90, requested_by=self.admin,
            start_datetime=dt(1), end_datetime=dt(3), status='allocated',
        )
        allocation.status = 'cancelled'
        allocation.save()
        self.assertEqual(self.resource.available_quantity(dt(1), dt(3)), 100)

    def test_returned_allocation_via_helper(self):
        allocation = ResourceAllocation.objects.create(
            resource=self.resource, quantity=90, requested_by=self.admin,
            start_datetime=dt(1), end_datetime=dt(3), status='allocated',
        )
        allocation.mark_returned()
        self.assertEqual(allocation.status, 'returned')
        self.assertIsNotNone(allocation.returned_at)
        self.assertEqual(self.resource.available_quantity(dt(1), dt(3)), 100)

    def test_damage_report_reduces_usable_quantity(self):
        DamageReport.objects.create(
            resource=self.resource, quantity_damaged=20, severity='major',
            description='Broken legs on 20 chairs', reported_by=self.admin,
        )
        self.assertEqual(self.resource.usable_quantity, 80)
        self.assertEqual(self.resource.available_quantity(dt(1), dt(2)), 80)

    def test_resolving_damage_report_restores_pool(self):
        report = DamageReport.objects.create(
            resource=self.resource, quantity_damaged=20, severity='major',
            description='Broken legs', reported_by=self.admin,
        )
        report.resolve(resolved_by=self.admin)
        self.assertEqual(self.resource.usable_quantity, 100)

    def test_damage_exceeding_total_quantity_rejected(self):
        with self.assertRaises(Exception):
            DamageReport.objects.create(
                resource=self.resource, quantity_damaged=999, severity='critical',
                description='Impossible amount', reported_by=self.admin,
            )


class ResourcePermissionViewTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(name='Projector X1', category='projectors', total_quantity=10)
        self.organizer = User.objects.create_user(username='rorg', password='pw12345!', role=User.ORGANIZER)
        self.staff = User.objects.create_user(username='rstaff', password='pw12345!', role=User.STAFF)
        self.vendor = User.objects.create_user(username='rvendor', password='pw12345!', role=User.VENDOR)
        self.participant = User.objects.create_user(username='rpart', password='pw12345!')

    def test_participant_cannot_create_resource(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('resources:resource_create'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_staff_can_create_resource(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('resources:resource_create'))
        self.assertEqual(response.status_code, 200)

    def test_organizer_can_reach_allocate_page(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('resources:resource_allocate_for', args=[self.resource.slug]))
        self.assertEqual(response.status_code, 200)

    def test_vendor_cannot_allocate(self):
        self.client.force_login(self.vendor)
        response = self.client.get(reverse('resources:resource_allocate_for', args=[self.resource.slug]))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_resource_list_publicly_visible(self):
        response = self.client.get(reverse('resources:resource_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Projector X1')

    def test_organizer_can_create_and_manage_own_resource_but_not_others(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('resources:resource_create'), {
            'name': 'Owned Speaker Set', 'category': 'sound_systems', 'total_quantity': 5, 'unit': 'unit',
        })
        self.assertTrue(Resource.objects.filter(name='Owned Speaker Set').exists())
        own_resource = Resource.objects.get(name='Owned Speaker Set')
        self.assertEqual(own_resource.created_by, self.organizer)

        response = self.client.get(reverse('resources:resource_update', args=[own_resource.slug]))
        self.assertEqual(response.status_code, 200)

        other_organizer = User.objects.create_user(username='rorg2', password='pw12345!', role=User.ORGANIZER)
        self.client.force_login(other_organizer)
        response = self.client.get(reverse('resources:resource_update', args=[own_resource.slug]))
        self.assertRedirects(response, reverse('resources:resource_detail', args=[own_resource.slug]))
        response = self.client.post(reverse('resources:resource_delete', args=[own_resource.slug]))
        self.assertTrue(Resource.objects.filter(pk=own_resource.pk).exists())


class ResourceAllocationFlowTests(TestCase):
    """End-to-end allocation request through the actual view/form."""

    def setUp(self):
        self.resource = Resource.objects.create(name='Round Table', category='tables', total_quantity=20)
        self.organizer = User.objects.create_user(username='torg', password='pw12345!', role=User.ORGANIZER)
        self.client.force_login(self.organizer)

    def _payload(self, **overrides):
        data = {
            'resource': self.resource.id, 'quantity': 15, 'purpose': 'Wedding setup',
            'start_datetime': dt(1).strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': dt(3).strftime('%Y-%m-%dT%H:%M'), 'notes': '',
        }
        data.update(overrides)
        return data

    def test_allocation_within_pool_succeeds(self):
        response = self.client.post(reverse('resources:resource_allocate_for', args=[self.resource.slug]), self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ResourceAllocation.objects.filter(resource=self.resource).count(), 1)

    def test_allocation_exceeding_pool_is_rejected_via_form(self):
        self.client.post(reverse('resources:resource_allocate_for', args=[self.resource.slug]), self._payload())
        response = self.client.post(
            reverse('resources:resource_allocate_for', args=[self.resource.slug]),
            self._payload(quantity=10, purpose='Second request'),
        )
        self.assertEqual(response.status_code, 200)  # rejected, form re-rendered
        self.assertEqual(ResourceAllocation.objects.filter(resource=self.resource).count(), 1)
