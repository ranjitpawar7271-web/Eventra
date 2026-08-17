from django import forms

from .models import PlatformSettings


class PlatformSettingsForm(forms.ModelForm):
    class Meta:
        model = PlatformSettings
        fields = ['site_name', 'support_email', 'allow_new_signups', 'maintenance_mode', 'maintenance_message']
        widgets = {'maintenance_message': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-control'})
