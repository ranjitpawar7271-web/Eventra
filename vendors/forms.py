from django import forms

from .models import (
    VendorContract, VendorDocument, VendorPayment, VendorProfile, VendorRating, VendorService,
)


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.FileInput)):
            field.widget.attrs.update({'class': 'form-control'})


class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = VendorProfile
        fields = ('company_name', 'service_type', 'contact_person', 'phone_number', 'address', 'description', 'logo')
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('service_type',))


class VendorServiceForm(forms.ModelForm):
    class Meta:
        model = VendorService
        fields = ('name', 'description', 'price', 'price_unit', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('price_unit',))


class VendorDocumentForm(forms.ModelForm):
    class Meta:
        model = VendorDocument
        fields = ('title', 'document_type', 'file')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('document_type',))


class VendorContractForm(forms.ModelForm):
    class Meta:
        model = VendorContract
        fields = ('event', 'title', 'description', 'amount', 'document', 'start_date', 'end_date')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
        self.fields['event'].required = False
        if user is not None and not user.is_superuser and user.role != user.SUPER_ADMIN:
            # Organizers only see their own events to attach a contract to.
            self.fields['event'].queryset = self.fields['event'].queryset.filter(organizer=user)


class VendorContractStatusForm(forms.ModelForm):
    class Meta:
        model = VendorContract
        fields = ('status',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].widget.attrs.update({'class': 'form-select'})


class VendorRatingForm(forms.ModelForm):
    class Meta:
        model = VendorRating
        fields = ('event', 'service_quality', 'delivery_time', 'comment')
        widgets = {'comment': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
        self.fields['event'].required = False
        self.fields['service_quality'].widget.attrs.update({'min': 1, 'max': 5})
        self.fields['delivery_time'].widget.attrs.update({'min': 1, 'max': 5})
        if user is not None and not user.is_superuser and user.role != user.SUPER_ADMIN:
            self.fields['event'].queryset = self.fields['event'].queryset.filter(organizer=user)


class VendorPaymentForm(forms.ModelForm):
    class Meta:
        model = VendorPayment
        fields = ('contract', 'amount', 'method', 'status', 'reference_note', 'payment_date')
        widgets = {'payment_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop('vendor', None)
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('method', 'status'))
        self.fields['contract'].required = False
        if vendor is not None:
            self.fields['contract'].queryset = vendor.contracts.all()
