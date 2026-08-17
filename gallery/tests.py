import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from users.models import User
from .models import Photo


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


def make_test_image():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), color='red').save(buffer, format='PNG')
    buffer.seek(0)
    return SimpleUploadedFile('test.png', buffer.read(), content_type='image/png')


class GalleryAccessTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.registered = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.stranger = User.objects.create_user(username='stranger1', password='pw12345!', role=User.PARTICIPANT)
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.event = make_event(self.organizer)
        Registration.objects.create(event=self.event, user=self.registered, status='confirmed')

    def test_gallery_is_public(self):
        # No login at all.
        response = self.client.get(reverse('gallery:event_gallery', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_upload'])

    def test_stranger_cannot_upload(self):
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.post(
            reverse('gallery:photo_upload', kwargs={'event_slug': self.event.slug}),
            {'image': make_test_image(), 'caption': 'nope'}
        )
        self.assertFalse(Photo.objects.filter(event=self.event).exists())

    def test_registered_user_can_upload(self):
        self.client.login(username='part1', password='pw12345!')
        self.client.post(
            reverse('gallery:photo_upload', kwargs={'event_slug': self.event.slug}),
            {'image': make_test_image(), 'caption': 'Great shot'}
        )
        photo = Photo.objects.get(event=self.event)
        self.assertEqual(photo.caption, 'Great shot')
        self.assertEqual(photo.uploaded_by, self.registered)

    def test_manager_can_upload(self):
        self.client.login(username='staff1', password='pw12345!')
        self.client.post(
            reverse('gallery:photo_upload', kwargs={'event_slug': self.event.slug}),
            {'image': make_test_image(), 'caption': ''}
        )
        self.assertTrue(Photo.objects.filter(event=self.event).exists())

    def test_only_manager_can_toggle_highlight(self):
        photo = Photo.objects.create(event=self.event, image=make_test_image(), uploaded_by=self.registered)

        self.client.login(username='part1', password='pw12345!')
        self.client.post(reverse('gallery:photo_toggle_highlight', kwargs={'pk': photo.pk}))
        photo.refresh_from_db()
        self.assertFalse(photo.is_highlight)  # uploader isn't a manager, blocked

        self.client.login(username='staff1', password='pw12345!')
        self.client.post(reverse('gallery:photo_toggle_highlight', kwargs={'pk': photo.pk}))
        photo.refresh_from_db()
        self.assertTrue(photo.is_highlight)

    def test_highlights_filter(self):
        Photo.objects.create(event=self.event, image=make_test_image(), uploaded_by=self.registered, is_highlight=True)
        Photo.objects.create(event=self.event, image=make_test_image(), uploaded_by=self.registered, is_highlight=False)

        response = self.client.get(reverse('gallery:event_gallery', kwargs={'event_slug': self.event.slug}) + '?filter=highlights')
        self.assertEqual(len(response.context['photos']), 1)

        response = self.client.get(reverse('gallery:event_gallery', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(len(response.context['photos']), 2)

    def test_uploader_can_delete_own_photo_stranger_cannot_delete_others(self):
        photo = Photo.objects.create(event=self.event, image=make_test_image(), uploaded_by=self.registered)

        self.client.login(username='stranger1', password='pw12345!')
        self.client.post(reverse('gallery:photo_delete', kwargs={'pk': photo.pk}))
        self.assertTrue(Photo.objects.filter(pk=photo.pk).exists())

        self.client.login(username='part1', password='pw12345!')
        self.client.post(reverse('gallery:photo_delete', kwargs={'pk': photo.pk}))
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())

    def test_manager_can_delete_any_photo(self):
        photo = Photo.objects.create(event=self.event, image=make_test_image(), uploaded_by=self.registered)
        self.client.login(username='staff1', password='pw12345!')
        self.client.post(reverse('gallery:photo_delete', kwargs={'pk': photo.pk}))
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())
