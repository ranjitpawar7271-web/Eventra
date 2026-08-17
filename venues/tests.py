from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from events.models import Event
from users.models import User
from .models import MaintenanceSchedule, Venue, VenueBooking

# Frozen once at import time so every dt(n) call in a test class refers to
# the exact same reference instant — using timezone.now() directly at each
# call site causes microsecond drift between calls, which can make
# "back-to-back, non-overlapping" windows look like they overlap.
_BASE_TIME = timezone.now()


def dt(hours_from_base):
    return _BASE_TIME + timedelta(hours=hours_from_base)


class VenueModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='vadmin', password='pw12345!', role=User.SUPER_ADMIN)
        self.venue = Venue.objects.create(
            name='Grand Hall', address='123 Main St', city='Pune', capacity=200, created_by=self.admin,
        )

    def test_slug_auto_generated(self):
        self.assertEqual(self.venue.slug, 'grand-hall')

    def test_is_available_true_when_no_bookings(self):
        self.assertTrue(self.venue.is_available(dt(1), dt(2)))

    def test_booking_blocks_overlapping_window(self):
        VenueBooking.objects.create(
            venue=self.venue, booked_by=self.admin, start_datetime=dt(1), end_datetime=dt(3), status='confirmed',
        )
        self.assertFalse(self.venue.is_available(dt(2), dt(4)))   # overlaps
        self.assertTrue(self.venue.is_available(dt(3), dt(5)))    # back-to-back, no overlap
        self.assertTrue(self.venue.is_available(dt(-2), dt(1)))   # ends exactly when booking starts

    def test_cancelled_booking_does_not_block(self):
        VenueBooking.objects.create(
            venue=self.venue, booked_by=self.admin, start_datetime=dt(1), end_datetime=dt(3), status='cancelled',
        )
        self.assertTrue(self.venue.is_available(dt(1), dt(3)))

    def test_maintenance_blocks_availability(self):
        MaintenanceSchedule.objects.create(
            venue=self.venue, reason='Deep cleaning', start_datetime=dt(5), end_datetime=dt(8), created_by=self.admin,
        )
        self.assertFalse(self.venue.is_available(dt(6), dt(7)))
        self.assertTrue(self.venue.is_available(dt(9), dt(10)))

    def test_booking_creation_rejects_conflicting_window(self):
        VenueBooking.objects.create(
            venue=self.venue, booked_by=self.admin, start_datetime=dt(1), end_datetime=dt(3), status='confirmed',
        )
        with self.assertRaises(Exception):
            VenueBooking.objects.create(
                venue=self.venue, booked_by=self.admin, start_datetime=dt(2), end_datetime=dt(4), status='confirmed',
            )

    def test_maintenance_rejects_when_confirmed_booking_overlaps(self):
        VenueBooking.objects.create(
            venue=self.venue, booked_by=self.admin, start_datetime=dt(1), end_datetime=dt(3), status='confirmed',
        )
        with self.assertRaises(Exception):
            MaintenanceSchedule.objects.create(
                venue=self.venue, reason='Repairs', start_datetime=dt(2), end_datetime=dt(4), created_by=self.admin,
            )


class VenuePermissionViewTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(name='Skyline Room', address='1 Sky Rd', city='Pune', capacity=50)
        self.organizer = User.objects.create_user(username='vorg', password='pw12345!', role=User.ORGANIZER)
        self.staff = User.objects.create_user(username='vstaff', password='pw12345!', role=User.STAFF)
        self.participant = User.objects.create_user(username='vpart', password='pw12345!')

    def test_participant_cannot_create_venue(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse('venues:venue_create'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_organizer_can_create_venue(self):
        # Organizers now manage venues for their own events (RBAC upgrade);
        # Super Admin/Staff still have unrestricted catalog access.
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('venues:venue_create'))
        self.assertEqual(response.status_code, 200)

    def test_organizer_cannot_edit_another_organizers_venue(self):
        other_organizer = User.objects.create_user(username='vorg2', password='pw12345!', role=User.ORGANIZER)
        owned_venue = Venue.objects.create(
            name='Owned Hall', address='2 Sky Rd', city='Pune', capacity=80, created_by=other_organizer,
        )
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('venues:venue_update', args=[owned_venue.slug]))
        self.assertRedirects(response, reverse('venues:venue_detail', args=[owned_venue.slug]))

    def test_organizer_can_edit_own_venue(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse('venues:venue_create'), {
            'name': 'My Venue', 'address': '5 Own St', 'city': 'Pune', 'capacity': 40,
        })
        own_venue = Venue.objects.get(name='My Venue')
        self.assertEqual(own_venue.created_by, self.organizer)
        response = self.client.get(reverse('venues:venue_update', args=[own_venue.slug]))
        self.assertEqual(response.status_code, 200)

    def test_staff_can_create_venue(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('venues:venue_create'))
        self.assertEqual(response.status_code, 200)

    def test_venue_list_publicly_visible(self):
        response = self.client.get(reverse('venues:venue_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Skyline Room')


class EventVenueIntegrationTests(TestCase):
    """Event <-> Venue booking sync and conflict detection through EventForm."""

    def setUp(self):
        self.category = Category.objects.create(name='Conference')
        self.venue = Venue.objects.create(name='Expo Center', address='9 Expo Ave', city='Pune', capacity=500)
        self.organizer = User.objects.create_user(username='eorg', password='pw12345!', role=User.ORGANIZER)
        self.client.force_login(self.organizer)

    def _event_payload(self, **overrides):
        data = {
            'title': 'Tech Summit', 'category': self.category.id, 'description': 'A great event',
            'location': 'Expo Center Hall A', 'venue': self.venue.id,
            'start_date': dt(24).strftime('%Y-%m-%dT%H:%M'),
            'end_date': dt(26).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 100, 'price': 0, 'status': 'published',
        }
        data.update(overrides)
        return data

    def test_creating_event_with_venue_creates_booking(self):
        response = self.client.post(reverse('events:event_create'), self._event_payload())
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Tech Summit')
        self.assertEqual(event.venue, self.venue)
        self.assertEqual(VenueBooking.objects.filter(event=event, status='confirmed').count(), 1)

    def test_second_event_conflicting_venue_time_is_rejected(self):
        self.client.post(reverse('events:event_create'), self._event_payload())
        response = self.client.post(reverse('events:event_create'), self._event_payload(title='Overlapping Expo'))
        self.assertEqual(response.status_code, 200)  # form re-rendered with error
        self.assertFalse(Event.objects.filter(title='Overlapping Expo').exists())

    def test_event_capacity_cannot_exceed_venue_capacity(self):
        response = self.client.post(reverse('events:event_create'), self._event_payload(capacity=999999))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Tech Summit').exists())
