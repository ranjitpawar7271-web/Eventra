from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from users.models import User
from .models import FavoriteEvent


def make_event(organizer, title='Test Event', status='published'):
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
        status=status,
    )


class FavoriteEventModelTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.user = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)

    def test_duplicate_favorite_rejected_at_db_level(self):
        FavoriteEvent.objects.create(user=self.user, event=self.event)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FavoriteEvent.objects.create(user=self.user, event=self.event)


class WishlistViewTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.user = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.other_user = User.objects.create_user(username='part2', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)

    def test_toggle_favorite_requires_login(self):
        response = self.client.post(reverse('wishlist:toggle_favorite', kwargs={'slug': self.event.slug}))
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(FavoriteEvent.objects.filter(event=self.event).exists())

    def test_toggle_favorite_adds_then_removes(self):
        self.client.login(username='part1', password='pw12345!')

        response = self.client.post(reverse('wishlist:toggle_favorite', kwargs={'slug': self.event.slug}))
        self.assertTrue(FavoriteEvent.objects.filter(user=self.user, event=self.event).exists())

        response = self.client.post(reverse('wishlist:toggle_favorite', kwargs={'slug': self.event.slug}))
        self.assertFalse(FavoriteEvent.objects.filter(user=self.user, event=self.event).exists())

    def test_toggle_redirects_to_next_param_when_provided(self):
        self.client.login(username='part1', password='pw12345!')
        target = reverse('events:event_list')
        response = self.client.post(
            reverse('wishlist:toggle_favorite', kwargs={'slug': self.event.slug}),
            {'next': target}
        )
        self.assertRedirects(response, target)

    def test_ajax_toggle_returns_json(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.post(
            reverse('wishlist:toggle_favorite', kwargs={'slug': self.event.slug}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'is_favorited': True, 'event': self.event.slug})

    def test_wishlist_list_only_shows_own_favorites(self):
        event2 = make_event(self.organizer, title='Second Event')
        FavoriteEvent.objects.create(user=self.user, event=self.event)
        FavoriteEvent.objects.create(user=self.other_user, event=event2)

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('wishlist:wishlist_list'))
        favorited_events = [f.event for f in response.context['favorites']]
        self.assertIn(self.event, favorited_events)
        self.assertNotIn(event2, favorited_events)

    def test_event_detail_reports_favorited_state(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('events:event_detail', kwargs={'slug': self.event.slug}))
        self.assertFalse(response.context['is_favorited'])

        FavoriteEvent.objects.create(user=self.user, event=self.event)
        response = self.client.get(reverse('events:event_detail', kwargs={'slug': self.event.slug}))
        self.assertTrue(response.context['is_favorited'])

    def test_event_list_reports_favorited_ids(self):
        FavoriteEvent.objects.create(user=self.user, event=self.event)
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('events:event_list'))
        self.assertIn(self.event.id, response.context['favorited_event_ids'])
