from django import forms

from events.models import Event
from .models import Task, TaskComment


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'priority', 'assigned_to', 'due_date']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if event is not None:
            # Only offer people actually tied to this event as assignees —
            # Staff/Super Admin (who can be assigned org-wide), the event's
            # organizer, and anyone already assigned to another task on
            # this board — rather than every user in the system.
            from django.contrib.auth import get_user_model
            from django.db.models import Q
            User = get_user_model()
            candidate_ids = set(
                Task.objects.filter(event=event).exclude(assigned_to__isnull=True)
                .values_list('assigned_to_id', flat=True)
            )
            candidate_ids.add(event.organizer_id)
            self.fields['assigned_to'].queryset = User.objects.filter(
                Q(id__in=candidate_ids) | Q(role__in=[User.STAFF, User.SUPER_ADMIN])
            ).distinct()
        _bootstrapify(self, select_fields=('priority', 'assigned_to'))


class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Add a comment...'}),
        }
