from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'venue_rating', 'organization_rating', 'comment']
        widgets = {
            'rating': forms.Select(choices=[(i, f"{i} star{'s' if i != 1 else ''}") for i in range(5, 0, -1)], attrs={'class': 'form-select'}),
            'venue_rating': forms.Select(choices=[('', '—')] + [(i, f"{i} star{'s' if i != 1 else ''}") for i in range(5, 0, -1)], attrs={'class': 'form-select'}),
            'organization_rating': forms.Select(choices=[('', '—')] + [(i, f"{i} star{'s' if i != 1 else ''}") for i in range(5, 0, -1)], attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Share your experience...'}),
        }
