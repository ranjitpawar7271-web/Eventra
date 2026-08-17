from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import Category


class CategoryPermissionTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='cadmin', password='pw12345!', role=User.SUPER_ADMIN)
        self.staff = User.objects.create_user(username='cstaff', password='pw12345!', role=User.STAFF)
        self.organizer = User.objects.create_user(username='corg1', password='pw12345!', role=User.ORGANIZER)
        self.other_organizer = User.objects.create_user(username='corg2', password='pw12345!', role=User.ORGANIZER)
        self.participant = User.objects.create_user(username='cpart', password='pw12345!', role=User.PARTICIPANT)

    def _create(self, username):
        self.client.login(username=username, password='pw12345!')
        return self.client.post(reverse('categories:category_create'), {
            'name': 'Music', 'description': '', 'icon': 'bi-music-note-beamed',
        })

    def test_participant_cannot_create_category(self):
        response = self._create('cpart')
        self.assertRedirects(response, reverse('dashboard:dashboard'))
        self.assertFalse(Category.objects.filter(name='Music').exists())

    def test_organizer_can_create_category_and_owns_it(self):
        self._create('corg1')
        self.assertTrue(Category.objects.filter(name='Music').exists())
        category = Category.objects.get(name='Music')
        self.assertEqual(category.created_by, self.organizer)

    def test_organizer_cannot_edit_or_delete_another_organizers_category(self):
        self._create('corg1')
        category = Category.objects.get(name='Music')

        self.client.login(username='corg2', password='pw12345!')
        response = self.client.get(reverse('categories:category_update', args=[category.slug]))
        self.assertRedirects(response, reverse('categories:category_list'))
        self.client.post(reverse('categories:category_delete', args=[category.slug]))
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_organizer_can_edit_and_delete_own_category(self):
        self._create('corg1')
        category = Category.objects.get(name='Music')

        self.client.login(username='corg1', password='pw12345!')
        self.client.post(reverse('categories:category_update', args=[category.slug]), {
            'name': 'Music & Arts', 'description': '', 'icon': 'bi-music-note-beamed',
        })
        category.refresh_from_db()
        self.assertEqual(category.name, 'Music & Arts')

        self.client.post(reverse('categories:category_delete', args=[category.slug]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_super_admin_and_staff_can_manage_any_category(self):
        self._create('corg1')
        category = Category.objects.get(name='Music')

        self.client.login(username='cstaff', password='pw12345!')
        self.client.post(reverse('categories:category_update', args=[category.slug]), {
            'name': 'Music (Staff Edited)', 'description': '', 'icon': 'bi-music-note-beamed',
        })
        category.refresh_from_db()
        self.assertEqual(category.name, 'Music (Staff Edited)')

        self.client.login(username='cadmin', password='pw12345!')
        self.client.post(reverse('categories:category_delete', args=[category.slug]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_category_list_publicly_visible(self):
        Category.objects.create(name='Tech', created_by=self.super_admin)
        response = self.client.get(reverse('categories:category_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tech')
