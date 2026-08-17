from django.test import TestCase
from django.urls import reverse

from events.models import Event
from categories.models import Category
from .models import User


class UserRoleModelTests(TestCase):
    """Module 1: role field behaviour and legacy is_organizer sync."""

    def test_default_role_is_participant(self):
        user = User.objects.create_user(username='alice', password='pw12345!')
        self.assertEqual(user.role, User.PARTICIPANT)
        self.assertFalse(user.is_organizer)

    def test_setting_role_organizer_syncs_is_organizer(self):
        user = User.objects.create_user(username='bob', password='pw12345!', role=User.ORGANIZER)
        self.assertTrue(user.is_organizer)

    def test_legacy_is_organizer_flag_promotes_role(self):
        user = User.objects.create_user(username='carol', password='pw12345!')
        user.is_organizer = True
        user.save(update_fields=['is_organizer'])
        user.refresh_from_db()
        self.assertEqual(user.role, User.ORGANIZER)

    def test_super_admin_helpers(self):
        admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        superuser = User.objects.create_superuser(username='root', password='pw12345!', email='r@example.com')
        participant = User.objects.create_user(username='dave', password='pw12345!')

        self.assertTrue(admin.is_super_admin)
        self.assertTrue(superuser.is_super_admin)
        self.assertFalse(participant.is_super_admin)

    def test_can_manage_events_by_role(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        vendor = User.objects.create_user(username='vend1', password='pw12345!', role=User.VENDOR)
        participant = User.objects.create_user(username='part1', password='pw12345!')

        self.assertTrue(organizer.can_manage_events)
        self.assertTrue(staff.can_manage_events)
        self.assertFalse(vendor.can_manage_events)
        self.assertFalse(participant.can_manage_events)


class SignupRoleFormTests(TestCase):
    """Sign-up form should only accept self-service roles."""

    def test_signup_with_valid_self_service_role(self):
        response = self.client.post(reverse('users:signup'), {
            'first_name': 'New', 'last_name': 'Vendor', 'username': 'newvendor',
            'email': 'v@example.com', 'role': User.VENDOR,
            'password1': 'S3cur3Pass!23', 'password2': 'S3cur3Pass!23',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='newvendor')
        self.assertEqual(user.role, User.VENDOR)

    def test_signup_cannot_self_assign_super_admin(self):
        response = self.client.post(reverse('users:signup'), {
            'first_name': 'Sneaky', 'last_name': 'User', 'username': 'sneaky',
            'email': 's@example.com', 'role': User.SUPER_ADMIN,
            'password1': 'S3cur3Pass!23', 'password2': 'S3cur3Pass!23',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='sneaky').exists())


class EventPermissionByRoleTests(TestCase):
    """Only roles that can_manage_events may create events."""

    def setUp(self):
        self.category = Category.objects.create(name='Tech')

    def test_participant_cannot_create_event(self):
        user = User.objects.create_user(username='part2', password='pw12345!')
        self.client.force_login(user)
        response = self.client.get(reverse('events:event_create'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))
        self.assertEqual(Event.objects.count(), 0)

    def test_organizer_can_reach_create_event_page(self):
        user = User.objects.create_user(username='org2', password='pw12345!', role=User.ORGANIZER)
        self.client.force_login(user)
        response = self.client.get(reverse('events:event_create'))
        self.assertEqual(response.status_code, 200)


class DashboardAdminPanelTests(TestCase):
    """Super Admins get the system-wide panel; other roles don't."""

    def test_participant_dashboard_has_no_admin_panel(self):
        user = User.objects.create_user(username='part3', password='pw12345!')
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard:dashboard'))
        self.assertNotIn('is_admin_view', response.context)

    def test_super_admin_dashboard_has_admin_panel(self):
        user = User.objects.create_user(username='admin2', password='pw12345!', role=User.SUPER_ADMIN)
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard:dashboard'))
        self.assertTrue(response.context['is_admin_view'])
        self.assertIn('sys_total_users', response.context)
