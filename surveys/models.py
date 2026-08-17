from django.conf import settings
from django.db import models


class Survey(models.Model):
    """One form scoped to an event — the same generic shape serves both
    spec items: "Live Polls" is a short, `is_live=True` survey shown to
    attendees during the event (refreshed by page reload, not a
    websocket push — this project doesn't have Django Channels wired in;
    see the Module 10 plan's note on polling vs. websockets for Chat/
    Announcements, same tradeoff applies here); "Feedback Forms" is the
    same model with `is_live=False`, left open after the event ends.
    One question/response/answer engine underneath both, rather than two
    parallel systems.
    """

    TYPE_POLL = 'poll'
    TYPE_FEEDBACK = 'feedback'
    SURVEY_TYPE_CHOICES = (
        (TYPE_POLL, 'Live Poll'),
        (TYPE_FEEDBACK, 'Feedback Form'),
    )

    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='surveys')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    survey_type = models.CharField(max_length=10, choices=SURVEY_TYPE_CHOICES, default=TYPE_FEEDBACK)
    is_open = models.BooleanField(
        default=True,
        help_text="Whether the survey currently accepts responses. Closing it doesn't delete anything already collected."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='surveys_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.event.title})"

    @property
    def response_count(self):
        return self.responses.count()


class Question(models.Model):
    TYPE_TEXT = 'text'
    TYPE_RATING = 'rating'
    TYPE_SINGLE_CHOICE = 'single_choice'
    TYPE_MULTIPLE_CHOICE = 'multiple_choice'
    QUESTION_TYPE_CHOICES = (
        (TYPE_TEXT, 'Open Text'),
        (TYPE_RATING, 'Rating (1–5)'),
        (TYPE_SINGLE_CHOICE, 'Single Choice'),
        (TYPE_MULTIPLE_CHOICE, 'Multiple Choice'),
    )

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions')
    question_text = models.CharField(max_length=300)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default=TYPE_TEXT)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.question_text

    @property
    def is_choice_type(self):
        return self.question_type in (self.TYPE_SINGLE_CHOICE, self.TYPE_MULTIPLE_CHOICE)


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    choice_text = models.CharField(max_length=150)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.choice_text


class Response(models.Model):
    """One person's completed submission to a Survey. One response per
    person per survey — enforced at the DB level — since re-submitting a
    poll/feedback form to change your answer isn't a supported flow here;
    a manager can see who's responded but not edit/delete someone else's
    answers on their behalf.
    """

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    respondent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='survey_responses')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        constraints = [
            models.UniqueConstraint(fields=['survey', 'respondent'], name='unique_survey_respondent')
        ]

    def __str__(self):
        return f"{self.respondent.username} → {self.survey.title}"


class Answer(models.Model):
    """One question's answer within a Response. Exactly one of
    `text_answer` / `rating_value` / `selected_choices` is populated,
    depending on the question's type — enforced in the view that builds
    these from the dynamic form, not at the DB level, since a CHECK
    constraint expressing "exactly one of three fields" is more friction
    than it's worth for a single-writer internal model like this.
    """

    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    text_answer = models.TextField(blank=True)
    rating_value = models.PositiveSmallIntegerField(null=True, blank=True)
    selected_choices = models.ManyToManyField(Choice, blank=True, related_name='answers')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['response', 'question'], name='unique_response_question')
        ]

    def __str__(self):
        return f"Answer to '{self.question}' by {self.response.respondent.username}"
