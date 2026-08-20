from django import forms
from django.utils import timezone

from .models import Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            'title', 'category', 'description', 'location', 'venue', 'organization',
            'start_date', 'end_date', 'capacity', 'price', 'image', 'status',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'start_date': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'end_date': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['start_date'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_date'].input_formats = ['%Y-%m-%dT%H:%M']

        self.fields['venue'].required = False
        self.fields['venue'].queryset = self.fields['venue'].queryset.filter(
            is_active=True
        )

        self.fields['organization'].required = False

        # Only offer organizations this user actually belongs to
        # (or all for a Super Admin).
        if user is not None and not getattr(user, 'is_super_admin', False):
            self.fields['organization'].queryset = (
                self.fields['organization']
                .queryset
                .filter(memberships__user=user)
                .distinct()
            )

        for name, field in self.fields.items():
            if name != 'image':
                field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        venue = cleaned_data.get('venue')

        # Event must start in the future.
        if start_date and start_date <= timezone.now():
            raise forms.ValidationError(
                "Event start date and time must be in the future."
            )

        # Event must end after it starts.
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError(
                "End date must be after the start date."
            )

        # Validate venue availability and capacity.
        if venue and start_date and end_date:
            # Exclude this event's own existing booking when editing
            # so re-saving the same event/venue/time does not create
            # a false conflict.
            existing_booking = None

            if self.instance and self.instance.pk:
                existing_booking = (
                    self.instance.venue_bookings
                    .filter(status='confirmed')
                    .first()
                )

            exclude_id = existing_booking.pk if existing_booking else None

            if not venue.is_available(
                start_date,
                end_date,
                exclude_booking_id=exclude_id
            ):
                raise forms.ValidationError(
                    f"{venue.name} is already booked or under maintenance "
                    "during that time window. Pick a different venue or time."
                )

            if (
                venue.capacity
                and cleaned_data.get('capacity')
                and cleaned_data['capacity'] > venue.capacity
            ):
                raise forms.ValidationError(
                    f"Event capacity ({cleaned_data['capacity']}) exceeds "
                    f"{venue.name}'s capacity ({venue.capacity})."
                )

        return cleaned_data