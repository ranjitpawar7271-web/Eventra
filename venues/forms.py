from django import forms

from .models import MaintenanceSchedule, Venue, VenueBooking


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = ('name', 'address', 'city', 'capacity', 'facilities', 'description', 'image', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ('image', 'is_active'):
                field.widget.attrs.update({'class': 'form-control'})
        self.fields['facilities'].widget.attrs['placeholder'] = 'e.g. Wi-Fi, Parking, Projector, AC'


class VenueBookingForm(forms.ModelForm):
    class Meta:
        model = VenueBooking
        fields = ('venue', 'purpose', 'start_datetime', 'end_datetime', 'notes')
        widgets = {
            'start_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['venue'].queryset = Venue.objects.filter(is_active=True)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        venue = cleaned_data.get('venue')
        start = cleaned_data.get('start_datetime')
        end = cleaned_data.get('end_datetime')
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after the start time.")
        if venue and start and end:
            exclude_id = self.instance.pk if self.instance else None
            if not venue.is_available(start, end, exclude_booking_id=exclude_id):
                raise forms.ValidationError(
                    f"{venue.name} is already booked or under maintenance during that time window."
                )
        return cleaned_data


class MaintenanceScheduleForm(forms.ModelForm):
    class Meta:
        model = MaintenanceSchedule
        fields = ('venue', 'reason', 'start_datetime', 'end_datetime')
        widgets = {
            'start_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        venue = cleaned_data.get('venue')
        start = cleaned_data.get('start_datetime')
        end = cleaned_data.get('end_datetime')
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after the start time.")
        if venue and start and end:
            overlapping = venue.bookings.filter(
                status='confirmed', start_datetime__lt=end, end_datetime__gt=start
            )
            if overlapping.exists():
                raise forms.ValidationError(
                    "There are confirmed bookings during that window. Cancel or move them first."
                )
        return cleaned_data
