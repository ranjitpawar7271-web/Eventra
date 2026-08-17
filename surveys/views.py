from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from events.models import Event, Registration
from users.models import User
from .forms import QuestionForm, SurveyForm, build_response_form
from .models import Answer, Choice, Question, Response, Survey

# Same organizer-owns-their-event-or-staff/admin shape used throughout
# (budget, sponsors, tasks, certificates).


def _can_manage(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


def _is_event_audience(user, event):
    """Managers, plus anyone with a confirmed registration for this
    event — the actual audience a poll/feedback form is meant for."""
    if not user.is_authenticated:
        return False
    if _can_manage(user, event):
        return True
    return Registration.objects.filter(event=event, user=user, status='confirmed').exists()


def _can_respond(user, survey):
    """Open to the event's confirmed registrants and to managers
    themselves (an organizer might reasonably want to test-fill their own
    poll). Not open to just anyone with an account — a feedback form is
    about this event's actual audience, not the whole platform."""
    return survey.is_open and _is_event_audience(user, survey.event)


@login_required
def survey_list(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    can_manage = _can_manage(request.user, event)
    surveys = event.surveys.all()

    if not can_manage:
        # Non-managers only ever see open surveys — a closed/draft survey
        # isn't something a participant needs to know existed.
        surveys = surveys.filter(is_open=True)
        if not _is_event_audience(request.user, event):
            # Not registered for this event at all — nothing to show them.
            surveys = surveys.none()

    responded_ids = set(
        Response.objects.filter(survey__in=surveys, respondent=request.user).values_list('survey_id', flat=True)
    )

    context = {
        'event': event,
        'surveys': surveys,
        'can_manage': can_manage,
        'responded_ids': responded_ids,
    }
    return render(request, 'surveys/survey_list.html', context)


@login_required
def survey_create(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_manage(request.user, event):
        messages.error(request, "You don't have permission to create surveys for this event.")
        return redirect('events:event_detail', slug=event.slug)

    if request.method == 'POST':
        form = SurveyForm(request.POST)
        if form.is_valid():
            survey = form.save(commit=False)
            survey.event = event
            survey.created_by = request.user
            survey.save()
            messages.success(request, f"'{survey.title}' created. Now add some questions.")
            return redirect('surveys:survey_manage', pk=survey.pk)
    else:
        form = SurveyForm()

    return render(request, 'surveys/survey_form.html', {'form': form, 'event': event})


@login_required
def survey_manage(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    if not _can_manage(request.user, survey.event):
        messages.error(request, "You don't have permission to manage this survey.")
        return redirect('events:event_detail', slug=survey.event.slug)

    if request.method == 'POST':
        question_form = QuestionForm(request.POST)
        if question_form.is_valid():
            next_order = survey.questions.count()
            question_form.save_with_choices(survey, order=next_order)
            messages.success(request, "Question added.")
            return redirect('surveys:survey_manage', pk=survey.pk)
    else:
        question_form = QuestionForm()

    context = {
        'survey': survey,
        'questions': survey.questions.prefetch_related('choices'),
        'question_form': question_form,
    }
    return render(request, 'surveys/survey_manage.html', context)


@login_required
@require_POST
def survey_toggle_open(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    if not _can_manage(request.user, survey.event):
        messages.error(request, "You don't have permission to manage this survey.")
        return redirect('events:event_detail', slug=survey.event.slug)

    survey.is_open = not survey.is_open
    survey.save(update_fields=['is_open'])
    messages.success(request, f"Survey is now {'open' if survey.is_open else 'closed'}.")
    return redirect('surveys:survey_manage', pk=survey.pk)


@login_required
def survey_delete(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    if not _can_manage(request.user, survey.event):
        messages.error(request, "You don't have permission to delete this survey.")
        return redirect('events:event_detail', slug=survey.event.slug)

    if request.method == 'POST':
        event_slug = survey.event.slug
        survey.delete()
        messages.success(request, "Survey deleted.")
        return redirect('surveys:survey_list', event_slug=event_slug)
    return render(request, 'surveys/survey_confirm_delete.html', {'survey': survey})


@login_required
def question_delete(request, pk):
    question = get_object_or_404(Question, pk=pk)
    survey = question.survey
    if not _can_manage(request.user, survey.event):
        messages.error(request, "You don't have permission to edit this survey.")
        return redirect('events:event_detail', slug=survey.event.slug)

    if request.method == 'POST':
        question.delete()
        messages.success(request, "Question removed.")
    return redirect('surveys:survey_manage', pk=survey.pk)


@login_required
def survey_respond(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    if not _can_respond(request.user, survey):
        messages.error(request, "This survey isn't available to you right now.")
        return redirect('surveys:survey_list', event_slug=survey.event.slug)

    if Response.objects.filter(survey=survey, respondent=request.user).exists():
        messages.info(request, "You've already responded to this survey.")
        return redirect('surveys:survey_list', event_slug=survey.event.slug)

    if not survey.questions.exists():
        messages.info(request, "This survey doesn't have any questions yet.")
        return redirect('surveys:survey_list', event_slug=survey.event.slug)

    if request.method == 'POST':
        form = build_response_form(survey, data=request.POST)
        if form.is_valid():
            response = Response.objects.create(survey=survey, respondent=request.user)
            for question in survey.questions.all():
                field_name = f"q_{question.id}"
                value = form.cleaned_data.get(field_name)
                if value in (None, '', []):
                    continue
                answer = Answer.objects.create(response=response, question=question)
                if question.question_type == Question.TYPE_TEXT:
                    answer.text_answer = value
                    answer.save(update_fields=['text_answer'])
                elif question.question_type == Question.TYPE_RATING:
                    answer.rating_value = int(value)
                    answer.save(update_fields=['rating_value'])
                elif question.question_type == Question.TYPE_SINGLE_CHOICE:
                    answer.selected_choices.set([value])
                elif question.question_type == Question.TYPE_MULTIPLE_CHOICE:
                    answer.selected_choices.set(value)
            messages.success(request, "Thanks — your response was recorded.")
            return redirect('surveys:survey_list', event_slug=survey.event.slug)
    else:
        form = build_response_form(survey)

    return render(request, 'surveys/survey_respond.html', {'survey': survey, 'form': form})


@login_required
def survey_results(request, pk):
    survey = get_object_or_404(Survey, pk=pk)
    if not _can_manage(request.user, survey.event):
        messages.error(request, "You don't have permission to view these results.")
        return redirect('events:event_detail', slug=survey.event.slug)

    question_results = []
    for question in survey.questions.prefetch_related('choices'):
        entry = {'question': question}
        if question.is_choice_type:
            entry['choice_counts'] = list(
                question.choices.annotate(count=Count('answers')).values('choice_text', 'count')
            )
        elif question.question_type == Question.TYPE_RATING:
            answers = Answer.objects.filter(question=question, rating_value__isnull=False)
            entry['average_rating'] = answers.aggregate(avg=Avg('rating_value'))['avg']
            entry['rating_count'] = answers.count()
        else:
            entry['text_answers'] = list(
                Answer.objects.filter(question=question).exclude(text_answer='').values_list('text_answer', flat=True)
            )
        question_results.append(entry)

    context = {
        'survey': survey,
        'question_results': question_results,
        'response_count': survey.response_count,
    }
    return render(request, 'surveys/survey_results.html', context)
