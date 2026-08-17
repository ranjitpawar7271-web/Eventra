from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=[(value, label) for value, label in User.ROLE_CHOICES
                 if value in User.SELF_SERVICE_ROLES],
        initial=User.PARTICIPANT,
        required=True,
        help_text="Super Admin and Staff accounts are granted by an administrator.",
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'role', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'role':
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

    def clean_role(self):
        role = self.cleaned_data['role']
        if role not in User.SELF_SERVICE_ROLES:
            raise forms.ValidationError("Invalid role selection.")
        return role


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'bio', 'profile_image')
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'profile_image':
                field.widget.attrs.update({'class': 'form-control'})
