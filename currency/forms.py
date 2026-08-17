from django import forms

from .models import Currency


def _bootstrapify(form):
    for name, field in form.fields.items():
        if not isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.update({'class': 'form-control'})


class CurrencyForm(forms.ModelForm):
    class Meta:
        model = Currency
        fields = ['code', 'name', 'symbol', 'rate_to_base', 'is_base']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean_code(self):
        return self.cleaned_data['code'].upper()
