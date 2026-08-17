from django.test import TestCase
from django.urls import reverse

from categories.models import Category
from users.models import User
from .backup_utils import RestoreValidationError, create_backup_json, execute_restore, validate_restore_content
from .health import get_system_health
from .models import BackupLog


class BackupRestoreRoundTripTests(TestCase):
    """The actual proof this feature works: back up real data, delete it,
    restore from the backup, and confirm it's genuinely back — not just
    that the views return 200."""

    def test_backup_then_restore_recovers_deleted_data(self):
        Category.objects.create(name='Music')
        Category.objects.create(name='Sports')
        self.assertEqual(Category.objects.count(), 2)

        content, object_count = create_backup_json()
        self.assertGreaterEqual(object_count, 2)

        Category.objects.all().delete()
        self.assertEqual(Category.objects.count(), 0)

        restored_count = execute_restore(content)
        self.assertEqual(restored_count, object_count)
        self.assertEqual(Category.objects.count(), 2)
        self.assertTrue(Category.objects.filter(name='Music').exists())
        self.assertTrue(Category.objects.filter(name='Sports').exists())

    def test_excluded_apps_are_not_in_backup(self):
        from django.contrib.sessions.models import Session
        content, _ = create_backup_json()
        self.assertNotIn('"model": "sessions.session"', content)
        self.assertNotIn('"model": "contenttypes.contenttype"', content)


class RestoreValidationTests(TestCase):
    def test_garbage_content_rejected(self):
        with self.assertRaises(RestoreValidationError):
            validate_restore_content("this is not json at all")

    def test_valid_json_but_not_a_fixture_rejected(self):
        with self.assertRaises(RestoreValidationError):
            validate_restore_content('{"hello": "world"}')

    def test_empty_fixture_rejected(self):
        with self.assertRaises(RestoreValidationError):
            validate_restore_content('[]')

    def test_valid_fixture_accepted_and_counted(self):
        Category.objects.create(name='Music')
        content, _ = create_backup_json()
        count = validate_restore_content(content)
        self.assertGreaterEqual(count, 1)

    def test_invalid_content_never_touches_database(self):
        """A validation failure must leave the database completely
        untouched — this is the core safety guarantee of validating
        before executing."""
        Category.objects.create(name='Untouched')
        before = Category.objects.count()
        with self.assertRaises(RestoreValidationError):
            execute_restore("garbage, not a fixture")
        self.assertEqual(Category.objects.count(), before)


class SystemHealthPermissionTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)

    def test_only_super_admin_can_view_system_health(self):
        """Stricter than most admin panels in this project — the module
        plan explicitly calls out system health as Super-Admin-only, not
        Staff-or-Super-Admin like FAQ/Announcements."""
        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('ops:system_health'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('ops:system_health'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='admin1', password='pw12345!')
        response = self.client.get(reverse('ops:system_health'))
        self.assertEqual(response.status_code, 200)

    def test_only_super_admin_can_download_backup(self):
        self.client.login(username='staff1', password='pw12345!')
        response = self.client.post(reverse('ops:backup_create'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='admin1', password='pw12345!')
        response = self.client.post(reverse('ops:backup_create'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_only_super_admin_can_access_restore_page(self):
        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('ops:restore_upload'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_backup_creates_audit_log_entry(self):
        self.client.login(username='admin1', password='pw12345!')
        self.client.post(reverse('ops:backup_create'))
        log = BackupLog.objects.filter(action='backup').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'success')
        self.assertEqual(log.performed_by, self.super_admin)


class RestoreUploadViewTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        self.client.login(username='admin1', password='pw12345!')

    def test_restore_requires_confirmation_checkbox(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        Category.objects.create(name='Music')
        content, _ = create_backup_json()
        upload = SimpleUploadedFile('backup.json', content.encode('utf-8'), content_type='application/json')

        response = self.client.post(reverse('ops:restore_upload'), {'backup_file': upload})
        # No 'confirm' field sent -> rejected before touching the DB.
        self.assertFalse(BackupLog.objects.filter(action='restore', status='success').exists())

    def test_invalid_upload_logs_failure_not_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile('bad.json', b'not valid json', content_type='application/json')
        self.client.post(reverse('ops:restore_upload'), {'backup_file': upload, 'confirm': 'yes'})
        log = BackupLog.objects.filter(action='restore').first()
        self.assertEqual(log.status, 'failed')

    def test_valid_upload_with_confirmation_restores_and_logs_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        Category.objects.create(name='Music')
        content, object_count = create_backup_json()
        Category.objects.all().delete()

        upload = SimpleUploadedFile('backup.json', content.encode('utf-8'), content_type='application/json')
        self.client.post(reverse('ops:restore_upload'), {'backup_file': upload, 'confirm': 'yes'})

        self.assertTrue(Category.objects.filter(name='Music').exists())
        log = BackupLog.objects.filter(action='restore').first()
        self.assertEqual(log.status, 'success')


class SystemHealthContentTests(TestCase):
    def test_get_system_health_reports_db_ok(self):
        health = get_system_health()
        self.assertTrue(health['db_ok'])
        self.assertIsInstance(health['model_counts'], list)
        self.assertGreater(len(health['model_counts']), 0)
