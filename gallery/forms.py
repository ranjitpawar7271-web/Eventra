from django import forms

from .models import Photo


class PhotoUploadForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ['image', 'caption']
        widgets = {
            'caption': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Add a caption (optional)'}),
        }
