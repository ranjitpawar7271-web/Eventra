from django import forms

from .models import EventSponsorship, Sponsor


def _bootstrapify(form, select_fields=()):
    """Same convention as vendors/forms.py — form.<field> is rendered bare
    in templates, so widget classes are applied here instead of per-field
    in HTML."""
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class SponsorForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        fields = [
            'company_name', 'logo', 'website', 'contact_person', 'email',
            'phone_number', 'description', 'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class EventSponsorshipForm(forms.ModelForm):
    class Meta:
        model = EventSponsorship
        fields = ['sponsor', 'package', 'amount', 'benefits', 'notes']
        widgets = {
            'benefits': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active sponsors when creating a new deal — an inactive
        # sponsor can still be viewed on existing sponsorships, just not
        # picked for new ones.
        self.fields['sponsor'].queryset = Sponsor.objects.filter(is_active=True)
        _bootstrapify(self, select_fields=('sponsor', 'package'))


class EventSponsorshipStatusForm(forms.ModelForm):
    class Meta:
        model = EventSponsorship
        fields = ['status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('status',))
