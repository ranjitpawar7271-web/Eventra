from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from users.models import User
from .models import Message


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


class ChatAccessTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.registered = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.stranger = User.objects.create_user(username='stranger1', password='pw12345!', role=User.PARTICIPANT)
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.event = make_event(self.organizer)
        Registration.objects.create(event=self.event, user=self.registered, status='confirmed')

    def test_stranger_cannot_view_chat(self):
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.get(reverse('chat:event_chat', kwargs={'event_slug': self.event.slug}))
        self.assertRedirects(response, self.event.get_absolute_url())

    def test_registered_user_can_view_chat(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('chat:event_chat', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(response.status_code, 200)

    def test_stranger_cannot_post(self):
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.post(
            reverse('chat:message_post', kwargs={'event_slug': self.event.slug}), {'body': 'hi'}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Message.objects.filter(event=self.event).exists())

    def test_registered_user_can_post_chat(self):
        self.client.login(username='part1', password='pw12345!')
        self.client.post(
            reverse('chat:message_post', kwargs={'event_slug': self.event.slug}), {'body': 'Hello everyone!'}
        )
        message = Message.objects.get(event=self.event)
        self.assertEqual(message.body, 'Hello everyone!')
        self.assertEqual(message.message_type, 'chat')

    def test_non_manager_cannot_post_announcement_gets_downgraded(self):
        self.client.login(username='part1', password='pw12345!')
        self.client.post(
            reverse('chat:message_post', kwargs={'event_slug': self.event.slug}),
            {'body': 'Fake announcement', 'message_type': 'announcement'}
        )
        message = Message.objects.get(event=self.event)
        self.assertEqual(message.message_type, 'chat')  # downgraded, not rejected

    def test_manager_can_post_announcement(self):
        self.client.login(username='staff1', password='pw12345!')
        self.client.post(
            reverse('chat:message_post', kwargs={'event_slug': self.event.slug}),
            {'body': 'Doors open at 9am', 'message_type': 'announcement'}
        )
        message = Message.objects.get(event=self.event)
        self.assertEqual(message.message_type, 'announcement')

    def test_empty_message_rejected(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.post(
            reverse('chat:message_post', kwargs={'event_slug': self.event.slug}), {'body': '   '}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Message.objects.filter(event=self.event).exists())

    def test_poll_only_returns_messages_after_given_id(self):
        m1 = Message.objects.create(event=self.event, sender=self.registered, body='first')
        m2 = Message.objects.create(event=self.event, sender=self.registered, body='second')
        m3 = Message.objects.create(event=self.event, sender=self.registered, body='third')

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(
            reverse('chat:message_poll', kwargs={'event_slug': self.event.slug}), {'after': m1.id}
        )
        bodies = [m['body'] for m in response.json()['messages']]
        self.assertEqual(bodies, ['second', 'third'])

    def test_stranger_cannot_poll(self):
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.get(reverse('chat:message_poll', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(response.status_code, 403)

    def test_sender_can_delete_own_message_stranger_cannot_delete_others(self):
        message = Message.objects.create(event=self.event, sender=self.registered, body='delete me')

        self.client.login(username='stranger1', password='pw12345!')
        self.client.post(reverse('chat:message_delete', kwargs={'pk': message.pk}))
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())

        self.client.login(username='part1', password='pw12345!')
        self.client.post(reverse('chat:message_delete', kwargs={'pk': message.pk}))
        self.assertFalse(Message.objects.filter(pk=message.pk).exists())

    def test_manager_can_delete_any_message(self):
        message = Message.objects.create(event=self.event, sender=self.registered, body='moderate me')
        self.client.login(username='staff1', password='pw12345!')
        self.client.post(reverse('chat:message_delete', kwargs={'pk': message.pk}))
        self.assertFalse(Message.objects.filter(pk=message.pk).exists())
