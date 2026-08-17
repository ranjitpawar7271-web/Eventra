from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from users.models import User
from .models import Task, TaskComment


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


class TaskModelTests(TestCase):
    def test_is_overdue(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        event = make_event(organizer)
        yesterday = timezone.now().date() - timedelta(days=1)
        tomorrow = timezone.now().date() + timedelta(days=1)

        overdue_task = Task.objects.create(event=event, title='Late', due_date=yesterday, status='todo')
        future_task = Task.objects.create(event=event, title='Future', due_date=tomorrow, status='todo')
        done_task = Task.objects.create(event=event, title='Done but late', due_date=yesterday, status='done')

        self.assertTrue(overdue_task.is_overdue)
        self.assertFalse(future_task.is_overdue)
        self.assertFalse(done_task.is_overdue)  # done tasks are never "overdue"


class TaskBoardPermissionTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.other_organizer = User.objects.create_user(username='org2', password='pw12345!', role=User.ORGANIZER)
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.volunteer = User.objects.create_user(username='vol1', password='pw12345!', role=User.PARTICIPANT)
        self.stranger = User.objects.create_user(username='stranger1', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)

    def test_only_organizer_staff_admin_can_add_tasks(self):
        self.client.login(username='org2', password='pw12345!')
        response = self.client.post(
            reverse('tasks:task_create', kwargs={'event_slug': self.event.slug}),
            {'title': 'Blocked task', 'description': '', 'priority': 'medium', 'due_date': ''}
        )
        self.assertFalse(Task.objects.filter(title='Blocked task').exists())

        self.client.login(username='org1', password='pw12345!')
        response = self.client.post(
            reverse('tasks:task_create', kwargs={'event_slug': self.event.slug}),
            {'title': 'Allowed task', 'description': '', 'priority': 'medium', 'due_date': ''}
        )
        self.assertTrue(Task.objects.filter(title='Allowed task').exists())

    def test_assigned_user_can_view_board_stranger_cannot(self):
        Task.objects.create(event=self.event, title='Setup chairs', assigned_to=self.volunteer)

        self.client.login(username='vol1', password='pw12345!')
        response = self.client.get(reverse('tasks:task_board', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(response.status_code, 200)

        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.get(reverse('tasks:task_board', kwargs={'event_slug': self.event.slug}))
        self.assertRedirects(response, self.event.get_absolute_url())

    def test_assignee_can_move_own_task_but_not_others(self):
        own_task = Task.objects.create(event=self.event, title='My task', assigned_to=self.volunteer, status='todo')
        other_task = Task.objects.create(event=self.event, title='Someone else task', status='todo')

        self.client.login(username='vol1', password='pw12345!')
        self.client.post(reverse('tasks:task_status_update', kwargs={'pk': own_task.pk}), {'status': 'done'})
        own_task.refresh_from_db()
        self.assertEqual(own_task.status, 'done')

        response = self.client.post(reverse('tasks:task_status_update', kwargs={'pk': other_task.pk}), {'status': 'done'})
        other_task.refresh_from_db()
        self.assertEqual(other_task.status, 'todo')  # blocked, unchanged

    def test_manager_can_delete_task_assignee_cannot(self):
        task = Task.objects.create(event=self.event, title='Delete me', assigned_to=self.volunteer)

        self.client.login(username='vol1', password='pw12345!')
        self.client.post(reverse('tasks:task_delete', kwargs={'pk': task.pk}))
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())  # not deleted

        self.client.login(username='org1', password='pw12345!')
        self.client.post(reverse('tasks:task_delete', kwargs={'pk': task.pk}))
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_assignee_can_comment_stranger_cannot(self):
        task = Task.objects.create(event=self.event, title='Comment target', assigned_to=self.volunteer)

        self.client.login(username='stranger1', password='pw12345!')
        self.client.post(reverse('tasks:task_comment_create', kwargs={'pk': task.pk}), {'comment': 'nope'})
        self.assertEqual(TaskComment.objects.filter(task=task).count(), 0)

        self.client.login(username='vol1', password='pw12345!')
        self.client.post(reverse('tasks:task_comment_create', kwargs={'pk': task.pk}), {'comment': 'On it'})
        self.assertEqual(TaskComment.objects.filter(task=task).count(), 1)

    def test_my_tasks_only_shows_assigned_tasks(self):
        Task.objects.create(event=self.event, title='Assigned to me', assigned_to=self.volunteer)
        Task.objects.create(event=self.event, title='Not mine')

        self.client.login(username='vol1', password='pw12345!')
        response = self.client.get(reverse('tasks:my_tasks'))
        titles = [t.title for t in response.context['tasks']]
        self.assertIn('Assigned to me', titles)
        self.assertNotIn('Not mine', titles)
