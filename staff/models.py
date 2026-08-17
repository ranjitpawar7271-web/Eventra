from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    """HR profile for a user with role=staff.

    Created via the Super-Admin-only "onboard staff" screen, which also
    promotes the target user's `role` to staff — this is the in-app
    replacement for assigning the Staff role through Django admin that
    Module 1 flagged as still being admin-only.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    employee_id = models.CharField(max_length=30, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    designation = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    skills = models.CharField(
        max_length=500, blank=True,
        help_text="Comma-separated list, e.g. 'Sound Engineering, First Aid, Crowd Control'"
    )
    hire_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True, help_text="Inactive staff are excluded from auto-assignment.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_profiles_onboarded'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['employee_id']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.employee_id})"

    def get_absolute_url(self):
        return reverse('staff:staff_detail', kwargs={'pk': self.pk})

    @property
    def skill_list(self):
        return [s.strip() for s in self.skills.split(',') if s.strip()]

    def is_available(self, start, end, exclude_shift_id=None):
        """No overlapping 'assigned' shift during [start, end)."""
        qs = self.shifts.filter(status='assigned', start_datetime__lt=end, end_datetime__gt=start)
        if exclude_shift_id:
            qs = qs.exclude(pk=exclude_shift_id)
        return not qs.exists()

    @staticmethod
    def find_available(start, end, department=None, skill=None):
        """Active staff with no conflicting shift during [start, end),
        optionally narrowed by department or a skill keyword. Used for
        both manual assignment suggestions and auto-assignment.
        """
        candidates = StaffProfile.objects.filter(is_active=True)
        if department:
            candidates = candidates.filter(department=department)
        if skill:
            candidates = candidates.filter(skills__icontains=skill)

        conflicting_ids = ShiftAssignment.objects.filter(
            status='assigned', start_datetime__lt=end, end_datetime__gt=start
        ).values_list('staff_id', flat=True)

        return candidates.exclude(pk__in=conflicting_ids)


class ShiftAssignment(models.Model):
    """Assigns one staff member to work a time window, optionally for an Event."""

    STATUS_CHOICES = (
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='shifts')
    event = models.ForeignKey(
        'events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_shifts'
    )
    title = models.CharField(max_length=200, help_text="e.g. 'Registration Desk', 'Sound Check'")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    notes = models.TextField(blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='shifts_assigned'
    )
    auto_assigned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f"{self.staff}: {self.title} ({self.start_datetime:%Y-%m-%d %H:%M})"

    def clean(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValidationError("End time must be after the start time.")
        if self.staff_id and self.status == 'assigned' and self.start_datetime and self.end_datetime:
            if not self.staff.is_available(self.start_datetime, self.end_datetime, exclude_shift_id=self.pk):
                raise ValidationError(
                    f"{self.staff} already has a conflicting shift during that time window."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AttendanceRecord(models.Model):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('half_day', 'Half Day'),
    )

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='attendance_records')
    shift = models.ForeignKey(
        ShiftAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_records'
    )
    date = models.DateField(default=timezone.now)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = ('staff', 'date')

    def __str__(self):
        return f"{self.staff} — {self.date} ({self.get_status_display()})"


class SalaryRecord(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
    )

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='salary_records')
    period_start = models.DateField()
    period_end = models.DateField()
    basic_amount = models.DecimalField(max_digits=10, decimal_places=2)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start']

    def __str__(self):
        return f"{self.staff} salary {self.period_start} – {self.period_end}"

    def clean(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError("Period end cannot be before period start.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def net_amount(self):
        return self.basic_amount + self.bonus - self.deductions
