from django import forms

from .models import FAQItem, PlatformAnnouncement, SupportRequest


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class FAQItemForm(forms.ModelForm):
    class Meta:
        model = FAQItem
        fields = ['question', 'answer', 'category', 'order', 'is_published']
        widgets = {'answer': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class PlatformAnnouncementForm(forms.ModelForm):
    class Meta:
        model = PlatformAnnouncement
        fields = ['title', 'body', 'is_active']
        widgets = {'body': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class SupportRequestForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = ['name', 'email', 'request_type', 'subject', 'message']
        widgets = {'message': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('request_type',))


class SupportRequestStatusForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = ['status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('status',))
