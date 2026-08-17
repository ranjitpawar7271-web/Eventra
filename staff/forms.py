from django import forms

from users.models import User
from .models import AttendanceRecord, Department, SalaryRecord, ShiftAssignment, StaffProfile


def _bootstrapify(form, select_fields=()):
    for name, field in form.fields.items():
        if name in select_fields:
            field.widget.attrs.update({'class': 'form-select'})
        elif not isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.update({'class': 'form-control'})


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ('name', 'description')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class StaffOnboardForm(forms.ModelForm):
    """Super-Admin-only: turns an existing user into staff. Picks the
    target user by username instead of a giant dropdown, and promotes
    their role to Staff on save (see StaffProfile.save() in the view)."""

    username = forms.CharField(
        label="User's username",
        help_text="The account to onboard as staff. They must already have signed up.",
    )

    class Meta:
        model = StaffProfile
        fields = ('employee_id', 'department', 'designation', 'phone_number', 'skills', 'hire_date', 'is_active')
        widgets = {'hire_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('department',))
        self.fields['skills'].widget.attrs['placeholder'] = 'e.g. Sound Engineering, First Aid, Crowd Control'

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError("No account found with that username.")
        if hasattr(user, 'staff_profile'):
            raise forms.ValidationError("This user is already onboarded as staff.")
        self.cleaned_data['user'] = user
        return username


class StaffProfileForm(forms.ModelForm):
    """Edit an existing staff profile (department/designation/etc, not the linked user)."""

    class Meta:
        model = StaffProfile
        fields = ('employee_id', 'department', 'designation', 'phone_number', 'skills', 'hire_date', 'is_active')
        widgets = {'hire_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('department',))


class ShiftAssignmentForm(forms.ModelForm):
    class Meta:
        model = ShiftAssignment
        fields = ('staff', 'event', 'title', 'start_datetime', 'end_datetime', 'notes')
        widgets = {
            'start_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['start_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_datetime'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['staff'].queryset = StaffProfile.objects.filter(is_active=True)
        self.fields['event'].required = False
        _bootstrapify(self, select_fields=('staff', 'event'))
        if user is not None and not user.is_superuser and user.role != User.SUPER_ADMIN:
            self.fields['event'].queryset = self.fields['event'].queryset.filter(organizer=user)

    def clean(self):
        cleaned_data = super().clean()
        staff = cleaned_data.get('staff')
        start = cleaned_data.get('start_datetime')
        end = cleaned_data.get('end_datetime')
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after the start time.")
        if staff and start and end:
            exclude_id = self.instance.pk if self.instance else None
            if not staff.is_available(start, end, exclude_shift_id=exclude_id):
                raise forms.ValidationError(f"{staff} already has a conflicting shift during that time window.")
        return cleaned_data


class AutoAssignForm(forms.Form):
    """Pick a time window (+ optional filters) and let the system find
    and assign the first available staff member automatically."""

    title = forms.CharField(max_length=200, initial='Event Duty')
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False)
    skill = forms.CharField(max_length=100, required=False, help_text="e.g. 'First Aid'")
    start_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    end_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        input_formats=['%Y-%m-%dT%H:%M'],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('department',))

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_datetime')
        end = cleaned_data.get('end_datetime')
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after the start time.")
        return cleaned_data


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ('date', 'status', 'check_in', 'check_out', 'notes')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'check_in': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'check_out': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['check_in'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['check_out'].input_formats = ['%Y-%m-%dT%H:%M']
        _bootstrapify(self, select_fields=('status',))


class SalaryRecordForm(forms.ModelForm):
    class Meta:
        model = SalaryRecord
        fields = ('period_start', 'period_end', 'basic_amount', 'bonus', 'deductions', 'status', 'payment_date')
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self, select_fields=('status',))
