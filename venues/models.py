from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Venue(models.Model):
    """A physical location that can be booked for events."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(help_text="Maximum number of people the venue can hold.")
    facilities = models.CharField(
        max_length=500, blank=True,
        help_text="Comma-separated list, e.g. 'Wi-Fi, Parking, Projector, AC'"
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='venue_images/', blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive venues are hidden from booking but keep their history."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='venues_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Venue.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('venues:venue_detail', kwargs={'slug': self.slug})

    @property
    def facility_list(self):
        return [f.strip() for f in self.facilities.split(',') if f.strip()]

    def is_available(self, start, end, exclude_booking_id=None, exclude_maintenance_id=None):
        """True if the venue has no confirmed booking or maintenance block
        overlapping [start, end)."""
        bookings = self.bookings.filter(status='confirmed', start_datetime__lt=end, end_datetime__gt=start)
        if exclude_booking_id:
            bookings = bookings.exclude(pk=exclude_booking_id)
        if bookings.exists():
            return False

        maintenance = self.maintenance_windows.filter(start_datetime__lt=end, end_datetime__gt=start)
        if exclude_maintenance_id:
            maintenance = maintenance.exclude(pk=exclude_maintenance_id)
        return not maintenance.exists()


class VenueBooking(models.Model):
    """Reserves a venue for a time window, typically tied to an Event."""

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    )

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='bookings')
    event = models.ForeignKey(
        'events.Event', on_delete=models.CASCADE, related_name='venue_bookings',
        null=True, blank=True,
        help_text="Linked automatically when an event selects this venue."
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='venue_bookings'
    )
    purpose = models.CharField(max_length=255, blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f"{self.venue.name}: {self.start_datetime:%Y-%m-%d %H:%M} - {self.end_datetime:%H:%M}"

    def clean(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValidationError("End time must be after the start time.")
        if self.venue_id and self.status == 'confirmed' and self.start_datetime and self.end_datetime:
            if not self.venue.is_available(self.start_datetime, self.end_datetime, exclude_booking_id=self.pk):
                raise ValidationError(
                    f"{self.venue.name} is already booked or under maintenance during that time window."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MaintenanceSchedule(models.Model):
    """Blocks a venue off (cleaning, repairs, etc.) so it can't be booked."""

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='maintenance_windows')
    reason = models.CharField(max_length=255)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenance_schedules_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime']
        verbose_name_plural = 'Maintenance schedules'

    def __str__(self):
        return f"{self.venue.name} maintenance: {self.reason}"

    def clean(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValidationError("End time must be after the start time.")
        if self.venue_id and self.start_datetime and self.end_datetime:
            overlapping_bookings = self.venue.bookings.filter(
                status='confirmed', start_datetime__lt=self.end_datetime, end_datetime__gt=self.start_datetime
            )
            if overlapping_bookings.exists():
                raise ValidationError(
                    "There are confirmed bookings during that window. Cancel or move them first."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
