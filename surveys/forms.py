from django import forms

from .models import Choice, Question, Survey


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class SurveyForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ['title', 'description', 'survey_type']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('survey_type',))


class QuestionForm(forms.ModelForm):
    """Adds a question and (for choice-type questions) its choices in one
    step. `choices_text` isn't a model field — it's a plain comma-
    separated CharField the view splits into real `Choice` rows, so
    building a poll question doesn't need a separate nested formset."""

    choices_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Option A, Option B, Option C'}),
        help_text="Comma-separated. Only used for Single Choice / Multiple Choice questions.",
    )

    class Meta:
        model = Question
        fields = ['question_text', 'question_type', 'required']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('question_type',))

    def clean(self):
        cleaned = super().clean()
        qtype = cleaned.get('question_type')
        choices_text = cleaned.get('choices_text', '').strip()
        if qtype in (Question.TYPE_SINGLE_CHOICE, Question.TYPE_MULTIPLE_CHOICE):
            options = [c.strip() for c in choices_text.split(',') if c.strip()]
            if len(options) < 2:
                raise forms.ValidationError(
                    "Choice questions need at least two comma-separated options."
                )
            cleaned['parsed_choices'] = options
        return cleaned

    def save_with_choices(self, survey, order=0):
        question = Question.objects.create(
            survey=survey,
            question_text=self.cleaned_data['question_text'],
            question_type=self.cleaned_data['question_type'],
            required=self.cleaned_data['required'],
            order=order,
        )
        for i, option in enumerate(self.cleaned_data.get('parsed_choices', [])):
            Choice.objects.create(question=question, choice_text=option, order=i)
        return question


def build_response_form(survey, data=None):
    """Builds a plain forms.Form with one dynamically-typed field per
    question on `survey` — this is the actual "generic form-builder"
    part: the field set isn't known until the survey/questions exist, so
    it can't be a fixed ModelForm."""

    class DynamicSurveyResponseForm(forms.Form):
        def __init__(self, *args, **inner_kwargs):
            super().__init__(*args, **inner_kwargs)
            for question in survey.questions.prefetch_related('choices').all():
                field_name = f"q_{question.id}"
                label = question.question_text
                required = question.required

                if question.question_type == Question.TYPE_TEXT:
                    self.fields[field_name] = forms.CharField(
                        label=label, required=required,
                        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
                    )
                elif question.question_type == Question.TYPE_RATING:
                    self.fields[field_name] = forms.ChoiceField(
                        label=label, required=required,
                        choices=[(str(i), str(i)) for i in range(1, 6)],
                        widget=forms.RadioSelect,
                    )
                elif question.question_type == Question.TYPE_SINGLE_CHOICE:
                    self.fields[field_name] = forms.ChoiceField(
                        label=label, required=required,
                        choices=[(str(c.id), c.choice_text) for c in question.choices.all()],
                        widget=forms.RadioSelect,
                    )
                elif question.question_type == Question.TYPE_MULTIPLE_CHOICE:
                    self.fields[field_name] = forms.MultipleChoiceField(
                        label=label, required=required,
                        choices=[(str(c.id), c.choice_text) for c in question.choices.all()],
                        widget=forms.CheckboxSelectMultiple,
                    )

    return DynamicSurveyResponseForm(data)
