from django import forms

from .models import EventBudget, Expense, RevenueEntry


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class EventBudgetForm(forms.ModelForm):
    class Meta:
        model = EventBudget
        fields = ('estimated_budget',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ('category', 'description', 'amount', 'date', 'receipt', 'status')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('category', 'status'))


class ExpenseStatusForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ('status',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].widget.attrs.update({'class': 'form-select form-select-sm'})


class RevenueEntryForm(forms.ModelForm):
    class Meta:
        model = RevenueEntry
        fields = ('source', 'sponsor_name', 'description', 'amount', 'date')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('source',))
        self.fields['sponsor_name'].required = False
        self.fields['description'].required = False
