from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from users.models import User
from .models import Answer, Choice, Question, Response, Survey


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


class SurveyModelTests(TestCase):
    def test_response_count(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        event = make_event(organizer)
        Registration.objects.create(event=event, user=participant, status='confirmed')
        survey = Survey.objects.create(event=event, title='Feedback', survey_type='feedback')
        self.assertEqual(survey.response_count, 0)
        Response.objects.create(survey=survey, respondent=participant)
        self.assertEqual(survey.response_count, 1)

    def test_duplicate_response_rejected(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        event = make_event(organizer)
        survey = Survey.objects.create(event=event, title='Feedback')
        Response.objects.create(survey=survey, respondent=participant)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Response.objects.create(survey=survey, respondent=participant)


class SurveyPermissionTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.other_organizer = User.objects.create_user(username='org2', password='pw12345!', role=User.ORGANIZER)
        self.registered = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.stranger = User.objects.create_user(username='stranger1', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)
        Registration.objects.create(event=self.event, user=self.registered, status='confirmed')

    def test_only_organizer_staff_admin_can_create_survey(self):
        self.client.login(username='org2', password='pw12345!')
        self.client.post(
            reverse('surveys:survey_create', kwargs={'event_slug': self.event.slug}),
            {'title': 'Blocked', 'description': '', 'survey_type': 'feedback'}
        )
        self.assertFalse(Survey.objects.filter(title='Blocked').exists())

        self.client.login(username='org1', password='pw12345!')
        self.client.post(
            reverse('surveys:survey_create', kwargs={'event_slug': self.event.slug}),
            {'title': 'Allowed', 'description': '', 'survey_type': 'feedback'}
        )
        self.assertTrue(Survey.objects.filter(title='Allowed').exists())

    def test_stranger_cannot_see_survey_in_list(self):
        Survey.objects.create(event=self.event, title='Open Survey', is_open=True)
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.get(reverse('surveys:survey_list', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(len(response.context['surveys']), 0)

    def test_registered_user_sees_open_survey_not_closed(self):
        Survey.objects.create(event=self.event, title='Open Survey', is_open=True)
        Survey.objects.create(event=self.event, title='Closed Survey', is_open=False)
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('surveys:survey_list', kwargs={'event_slug': self.event.slug}))
        titles = [s.title for s in response.context['surveys']]
        self.assertIn('Open Survey', titles)
        self.assertNotIn('Closed Survey', titles)

    def test_stranger_cannot_respond(self):
        survey = Survey.objects.create(event=self.event, title='Feedback', is_open=True)
        Question.objects.create(survey=survey, question_text='How was it?', question_type='text')
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.post(
            reverse('surveys:survey_respond', kwargs={'pk': survey.pk}),
            {}
        )
        self.assertFalse(Response.objects.filter(survey=survey).exists())

    def test_registered_user_can_respond_once(self):
        survey = Survey.objects.create(event=self.event, title='Feedback', is_open=True)
        q_text = Question.objects.create(survey=survey, question_text='Comments?', question_type='text', required=False)
        self.client.login(username='part1', password='pw12345!')
        self.client.post(
            reverse('surveys:survey_respond', kwargs={'pk': survey.pk}),
            {f'q_{q_text.id}': 'Great event!'}
        )
        self.assertEqual(Response.objects.filter(survey=survey, respondent=self.registered).count(), 1)
        answer = Answer.objects.get(response__survey=survey, question=q_text)
        self.assertEqual(answer.text_answer, 'Great event!')

        # Second attempt is blocked, not a duplicate response
        self.client.post(
            reverse('surveys:survey_respond', kwargs={'pk': survey.pk}),
            {f'q_{q_text.id}': 'Trying again'}
        )
        self.assertEqual(Response.objects.filter(survey=survey, respondent=self.registered).count(), 1)

    def test_cannot_respond_to_closed_survey(self):
        survey = Survey.objects.create(event=self.event, title='Closed', is_open=False)
        Question.objects.create(survey=survey, question_text='Q', question_type='text', required=False)
        self.client.login(username='part1', password='pw12345!')
        response = self.client.post(reverse('surveys:survey_respond', kwargs={'pk': survey.pk}), {})
        self.assertFalse(Response.objects.filter(survey=survey).exists())

    def test_single_choice_response_records_selected_choice(self):
        survey = Survey.objects.create(event=self.event, title='Poll', survey_type='poll', is_open=True)
        question = Question.objects.create(survey=survey, question_text='Best session?', question_type='single_choice')
        c1 = Choice.objects.create(question=question, choice_text='Session A')
        c2 = Choice.objects.create(question=question, choice_text='Session B')

        self.client.login(username='part1', password='pw12345!')
        self.client.post(
            reverse('surveys:survey_respond', kwargs={'pk': survey.pk}),
            {f'q_{question.id}': str(c1.id)}
        )
        answer = Answer.objects.get(response__survey=survey, question=question)
        self.assertEqual(list(answer.selected_choices.all()), [c1])

    def test_only_manager_can_view_results(self):
        survey = Survey.objects.create(event=self.event, title='Feedback')
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('surveys:survey_results', kwargs={'pk': survey.pk}))
        self.assertRedirects(response, self.event.get_absolute_url())

        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('surveys:survey_results', kwargs={'pk': survey.pk}))
        self.assertEqual(response.status_code, 200)


class QuestionBuilderTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.event = make_event(self.organizer)
        self.survey = Survey.objects.create(event=self.event, title='Feedback')

    def test_choice_question_requires_at_least_two_options(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.post(
            reverse('surveys:survey_manage', kwargs={'pk': self.survey.pk}),
            {'question_text': 'Pick one', 'question_type': 'single_choice', 'required': True, 'choices_text': 'Only One'}
        )
        self.assertEqual(Question.objects.filter(survey=self.survey).count(), 0)

    def test_choice_question_creates_choices_from_comma_separated_text(self):
        self.client.login(username='org1', password='pw12345!')
        self.client.post(
            reverse('surveys:survey_manage', kwargs={'pk': self.survey.pk}),
            {'question_text': 'Pick one', 'question_type': 'single_choice', 'required': True, 'choices_text': 'A, B, C'}
        )
        question = Question.objects.get(survey=self.survey)
        self.assertEqual(question.choices.count(), 3)
        self.assertEqual(list(question.choices.values_list('choice_text', flat=True)), ['A', 'B', 'C'])
