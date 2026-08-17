from django import forms

from .models import WorkflowSettings


class ApprovalDecisionForm(forms.Form):
    comment = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        help_text="Optional — especially useful when rejecting."
    )


class WorkflowSettingsForm(forms.ModelForm):
    class Meta:
        model = WorkflowSettings
        fields = ('require_event_approval',)
        widgets = {
            'require_event_approval': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BroadcastForm(forms.Form):
    message = forms.CharField(
        max_length=255, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        help_text="Sent as an in-app + email notification to every user."
    )
    link = forms.CharField(
        max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="Optional. e.g. /events/ or a full URL."
    )
