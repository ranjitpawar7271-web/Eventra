from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import FAQItem, PlatformAnnouncement, SupportRequest


class FAQPermissionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)

    def test_faq_list_is_public(self):
        FAQItem.objects.create(question='Q1', answer='A1', is_published=True)
        response = self.client.get(reverse('support:faq_list'))
        self.assertEqual(response.status_code, 200)

    def test_unpublished_faq_hidden_from_non_managers(self):
        FAQItem.objects.create(question='Draft Q', answer='A', is_published=False)
        response = self.client.get(reverse('support:faq_list'))
        self.assertEqual(len(response.context['items']), 0)

        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('support:faq_list'))
        self.assertEqual(len(response.context['items']), 1)

    def test_only_staff_admin_can_create_faq(self):
        self.client.login(username='part1', password='pw12345!')
        self.client.post(reverse('support:faq_create'), {
            'question': 'Blocked?', 'answer': 'No.', 'category': '', 'order': 0, 'is_published': True
        })
        self.assertFalse(FAQItem.objects.filter(question='Blocked?').exists())

        self.client.login(username='staff1', password='pw12345!')
        self.client.post(reverse('support:faq_create'), {
            'question': 'Allowed?', 'answer': 'Yes.', 'category': '', 'order': 0, 'is_published': True
        })
        self.assertTrue(FAQItem.objects.filter(question='Allowed?').exists())


class AnnouncementPermissionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)

    def test_announcement_list_is_public_and_hides_inactive(self):
        PlatformAnnouncement.objects.create(title='Active', body='body', is_active=True)
        PlatformAnnouncement.objects.create(title='Inactive', body='body', is_active=False)
        response = self.client.get(reverse('support:announcement_list'))
        titles = [a.title for a in response.context['announcements']]
        self.assertIn('Active', titles)
        self.assertNotIn('Inactive', titles)

    def test_organizer_cannot_create_platform_announcement(self):
        """Platform announcements are a platform-level permission, not the
        usual organizer-owns-their-event check — an Organizer has no
        special standing here."""
        self.client.login(username='org1', password='pw12345!')
        self.client.post(reverse('support:announcement_create'), {
            'title': 'Blocked', 'body': 'x', 'is_active': True
        })
        self.assertFalse(PlatformAnnouncement.objects.filter(title='Blocked').exists())

    def test_staff_can_create_platform_announcement(self):
        self.client.login(username='staff1', password='pw12345!')
        self.client.post(reverse('support:announcement_create'), {
            'title': 'Allowed', 'body': 'x', 'is_active': True
        })
        self.assertTrue(PlatformAnnouncement.objects.filter(title='Allowed').exists())


class SupportRequestTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.other = User.objects.create_user(username='other1', password='pw12345!', role=User.PARTICIPANT)

    def test_anonymous_visitor_can_submit(self):
        response = self.client.post(reverse('support:support_contact'), {
            'name': 'Anon', 'email': 'anon@example.com', 'request_type': 'support',
            'subject': 'Help', 'message': 'Something is broken',
        })
        req = SupportRequest.objects.get(subject='Help')
        self.assertIsNone(req.user)
        self.assertEqual(req.status, 'open')

    def test_logged_in_submission_is_linked_to_user(self):
        self.client.login(username='part1', password='pw12345!')
        self.client.post(reverse('support:support_contact'), {
            'name': 'Part One', 'email': 'part1@example.com', 'request_type': 'feedback',
            'subject': 'Idea', 'message': 'You should add X',
        })
        req = SupportRequest.objects.get(subject='Idea')
        self.assertEqual(req.user, self.participant)

    def test_my_requests_only_shows_own(self):
        SupportRequest.objects.create(
            user=self.participant, name='P1', email='p1@example.com',
            subject='Mine', message='x'
        )
        SupportRequest.objects.create(
            user=self.other, name='O1', email='o1@example.com',
            subject='Not mine', message='x'
        )
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('support:my_support_requests'))
        subjects = [r.subject for r in response.context['requests']]
        self.assertIn('Mine', subjects)
        self.assertNotIn('Not mine', subjects)

    def test_only_staff_admin_can_access_inbox(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('support:support_inbox'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('support:support_inbox'))
        self.assertEqual(response.status_code, 200)

    def test_status_update_sets_resolved_by(self):
        req = SupportRequest.objects.create(
            name='P1', email='p1@example.com', subject='Fix me', message='x'
        )
        self.client.login(username='staff1', password='pw12345!')
        self.client.post(
            reverse('support:support_request_status_update', kwargs={'pk': req.pk}),
            {'status': 'resolved'}
        )
        req.refresh_from_db()
        self.assertEqual(req.status, 'resolved')
        self.assertEqual(req.resolved_by, self.staff)

    def test_inbox_status_filter(self):
        SupportRequest.objects.create(name='A', email='a@x.com', subject='Open one', message='x', status='open')
        SupportRequest.objects.create(name='B', email='b@x.com', subject='Resolved one', message='x', status='resolved')
        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('support:support_inbox') + '?status=resolved')
        subjects = [r.subject for r in response.context['requests']]
        self.assertEqual(subjects, ['Resolved one'])
