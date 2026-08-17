from django import forms

from .models import DamageReport, Resource, ResourceAllocation


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ('name', 'category', 'description', 'total_quantity', 'unit', 'image', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ('image', 'is_active'):
                field.widget.attrs.update({'class': 'form-control'})
        self.fields['category'].widget.attrs['class'] = 'form-select'


class ResourceAllocationForm(forms.ModelForm):
    class Meta:
        model = ResourceAllocation
        fields = ('resource', 'quantity', 'purpose', 'start_datetime', 'end_datetime', 'notes')
        widgets = {
            'start_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['resource'].queryset = Resource.objects.filter(is_active=True)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        resource = cleaned_data.get('resource')
        quantity = cleaned_data.get('quantity')
        start = cleaned_data.get('start_datetime')
        end = cleaned_data.get('end_datetime')

        if start and end and end <= start:
            raise forms.ValidationError("End time must be after the start time.")

        if resource and quantity and start and end:
            exclude_id = self.instance.pk if self.instance else None
            available = resource.available_quantity(start, end, exclude_allocation_id=exclude_id)
            if quantity > available:
                raise forms.ValidationError(
                    f"Only {available} {resource.unit} of {resource.name} are available "
                    f"during that time window (requested {quantity})."
                )
        return cleaned_data


class DamageReportForm(forms.ModelForm):
    class Meta:
        model = DamageReport
        fields = ('resource', 'allocation', 'quantity_damaged', 'severity', 'description')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        resource = kwargs.pop('resource', None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
        self.fields['severity'].widget.attrs['class'] = 'form-select'
        self.fields['allocation'].required = False
        if resource:
            self.fields['resource'].initial = resource
            self.fields['resource'].widget = forms.HiddenInput()
            self.fields['allocation'].queryset = resource.allocations.filter(status='allocated')
        else:
            self.fields['allocation'].queryset = self.fields['allocation'].queryset.none()

    def clean(self):
        cleaned_data = super().clean()
        resource = cleaned_data.get('resource')
        quantity_damaged = cleaned_data.get('quantity_damaged')
        if resource and quantity_damaged and quantity_damaged > resource.total_quantity:
            raise forms.ValidationError("Damaged quantity can't exceed the resource's total quantity.")
        return cleaned_data
