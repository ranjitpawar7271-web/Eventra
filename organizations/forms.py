from django import forms

from users.models import User
from .models import Organization, OrganizationMembership


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput,)):
            field.widget.attrs.update({'class': 'form-control'})


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class MembershipForm(forms.Form):
    """Plain Form, not a ModelForm — the choice of *which roles are even
    offered* depends on who's submitting it (see the `restrict_to_non_owner`
    flag), which a ModelForm's fixed `choices` can't express per-instance
    without extra ceremony."""

    username = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=OrganizationMembership.ROLE_CHOICES)

    def __init__(self, *args, restrict_to_non_owner=False, **kwargs):
        super().__init__(*args, **kwargs)
        if restrict_to_non_owner:
            # An org Admin (not Owner, not Super Admin) can add members and
            # promote to Admin, but can't grant Owner — that would be a
            # privilege escalation path from "admin" to "owner" with no
            # Super Admin or existing Owner in the loop.
            self.fields['role'].choices = [
                c for c in OrganizationMembership.ROLE_CHOICES if c[0] != OrganizationMembership.ROLE_OWNER
            ]
        _bootstrapify(self, select_fields=('role',))

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if not User.objects.filter(username=username).exists():
            raise forms.ValidationError("No user with that username exists.")
        return username
