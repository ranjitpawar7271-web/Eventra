from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import PlatformSettings


class PlatformSettingsSingletonTests(TestCase):
    def test_load_creates_default_row(self):
        self.assertEqual(PlatformSettings.objects.count(), 0)
        settings_obj = PlatformSettings.load()
        self.assertEqual(PlatformSettings.objects.count(), 1)
        self.assertFalse(settings_obj.maintenance_mode)

    def test_save_always_uses_pk_one(self):
        s1 = PlatformSettings.load()
        s1.site_name = 'Renamed'
        s1.save()
        self.assertEqual(PlatformSettings.objects.count(), 1)
        self.assertEqual(PlatformSettings.objects.first().site_name, 'Renamed')

    def test_delete_is_a_no_op(self):
        settings_obj = PlatformSettings.load()
        settings_obj.delete()
        self.assertEqual(PlatformSettings.objects.count(), 1)


class PlatformSettingsPermissionTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)

    def test_only_super_admin_can_edit_settings(self):
        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('platform_settings:settings_edit'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='admin1', password='pw12345!')
        response = self.client.get(reverse('platform_settings:settings_edit'))
        self.assertEqual(response.status_code, 200)

    def test_editing_settings_records_who_updated_it(self):
        self.client.login(username='admin1', password='pw12345!')
        self.client.post(reverse('platform_settings:settings_edit'), {
            'site_name': 'New Name', 'support_email': 'help@example.com',
            'allow_new_signups': True, 'maintenance_mode': False, 'maintenance_message': 'brb',
        })
        settings_obj = PlatformSettings.load()
        self.assertEqual(settings_obj.site_name, 'New Name')
        self.assertEqual(settings_obj.updated_by, self.super_admin)


class MaintenanceModeMiddlewareTests(TestCase):
    """Confirms the actual end-to-end behavior of flipping the switch —
    not just that the model field exists, but that ordinary requests are
    genuinely blocked for everyone except Super Admins, and that the
    switch being off (the default) changes nothing for anyone."""

    def setUp(self):
        self.super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)

    def test_maintenance_mode_off_by_default_does_not_block_anyone(self):
        response = self.client.get(reverse('events:event_list'))
        self.assertEqual(response.status_code, 200)

    def test_maintenance_mode_on_blocks_anonymous_visitor(self):
        settings_obj = PlatformSettings.load()
        settings_obj.maintenance_mode = True
        settings_obj.save()

        response = self.client.get(reverse('events:event_list'))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "We'll be right back", status_code=503)

    def test_maintenance_mode_on_blocks_regular_logged_in_user(self):
        settings_obj = PlatformSettings.load()
        settings_obj.maintenance_mode = True
        settings_obj.save()

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('events:event_list'))
        self.assertEqual(response.status_code, 503)

    def test_maintenance_mode_on_does_not_block_super_admin(self):
        settings_obj = PlatformSettings.load()
        settings_obj.maintenance_mode = True
        settings_obj.save()

        self.client.login(username='admin1', password='pw12345!')
        response = self.client.get(reverse('events:event_list'))
        self.assertEqual(response.status_code, 200)

    def test_maintenance_mode_on_does_not_block_login_page(self):
        """Without this exemption, turning maintenance mode on could lock
        everyone out of the one page that turns it back off."""
        settings_obj = PlatformSettings.load()
        settings_obj.maintenance_mode = True
        settings_obj.save()

        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)
