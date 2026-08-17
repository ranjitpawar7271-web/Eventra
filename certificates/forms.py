from django import forms

from .models import Certificate


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class CertificateIssueForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = ['cert_type', 'title', 'badge_level']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('cert_type', 'badge_level'))
