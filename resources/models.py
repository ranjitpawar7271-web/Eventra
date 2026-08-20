from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from event_management.validators import (
    safe_upload_to, validate_image_contents, validate_image_extension, validate_image_size,
)


class Resource(models.Model):
    """A pool of physical, allocatable inventory (chairs, projectors, etc).

    Resources are quantity-based rather than single-item like Venues: a
    Resource represents N identical units, and allocations draw from that
    pool for a time window instead of reserving the whole thing exclusively.
    """

    CATEGORY_CHOICES = (
        ('chairs', 'Chairs'),
        ('tables', 'Tables'),
        ('projectors', 'Projectors'),
        ('sound_systems', 'Sound Systems'),
        ('lights', 'Lights'),
        ('vehicles', 'Vehicles'),
        ('generators', 'Generators'),
        ('decoration', 'Decoration Items'),
        ('other', 'Other'),
    )

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    description = models.TextField(blank=True)
    total_quantity = models.PositiveIntegerField(help_text="Total units owned/available in inventory.")
    unit = models.CharField(max_length=30, default='pcs', help_text="e.g. pcs, sets, units")
    image = models.ImageField(
        upload_to=safe_upload_to('resource_images'), blank=True, null=True,
        validators=[validate_image_extension, validate_image_size, validate_image_contents],
    )
    is_active = models.BooleanField(default=True, help_text="Inactive resources are hidden from allocation.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resources_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.total_quantity} {self.unit})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Resource.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('resources:resource_detail', kwargs={'slug': self.slug})

    @property
    def damaged_quantity(self):
        """Units currently out of service (reported or under repair)."""
        total = self.damage_reports.filter(
            status__in=['reported', 'under_repair']
        ).aggregate(Sum('quantity_damaged'))['quantity_damaged__sum']
        return total or 0

    @property
    def usable_quantity(self):
        """Total units minus anything currently out of service."""
        return max(self.total_quantity - self.damaged_quantity, 0)

    def allocated_quantity(self, start, end, exclude_allocation_id=None):
        """Units already promised to other allocations overlapping [start, end)."""
        qs = self.allocations.filter(status='allocated', start_datetime__lt=end, end_datetime__gt=start)
        if exclude_allocation_id:
            qs = qs.exclude(pk=exclude_allocation_id)
        return qs.aggregate(Sum('quantity'))['quantity__sum'] or 0

    def available_quantity(self, start, end, exclude_allocation_id=None):
        """How many units are free to allocate during [start, end)."""
        allocated = self.allocated_quantity(start, end, exclude_allocation_id=exclude_allocation_id)
        return max(self.usable_quantity - allocated, 0)

    def is_available(self, start, end, quantity, exclude_allocation_id=None):
        return self.available_quantity(start, end, exclude_allocation_id=exclude_allocation_id) >= quantity


class ResourceAllocation(models.Model):
    """Reserves N units of a Resource for a time window."""

    STATUS_CHOICES = (
        ('allocated', 'Allocated'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    )

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='allocations')
    event = models.ForeignKey(
        'events.Event', on_delete=models.CASCADE, related_name='resource_allocations',
        null=True, blank=True,
    )
    quantity = models.PositiveIntegerField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resource_allocations'
    )
    purpose = models.CharField(max_length=255, blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='allocated')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f"{self.quantity}x {self.resource.name}: {self.start_datetime:%Y-%m-%d %H:%M}"

    def clean(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValidationError("End time must be after the start time.")
        if not self.quantity or self.quantity <= 0:
            raise ValidationError("Quantity must be at least 1.")
        if self.resource_id and self.status == 'allocated' and self.start_datetime and self.end_datetime:
            if not self.resource.is_available(
                self.start_datetime, self.end_datetime, self.quantity, exclude_allocation_id=self.pk
            ):
                available = self.resource.available_quantity(
                    self.start_datetime, self.end_datetime, exclude_allocation_id=self.pk
                )
                raise ValidationError(
                    f"Only {available} {self.resource.unit} of {self.resource.name} are available "
                    f"during that time window (requested {self.quantity})."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def mark_returned(self):
        self.status = 'returned'
        self.returned_at = timezone.now()
        self.save()


class DamageReport(models.Model):
    """Tracks damaged/lost units so they're pulled out of the allocatable pool."""

    SEVERITY_CHOICES = (
        ('minor', 'Minor'),
        ('major', 'Major'),
        ('critical', 'Critical'),
    )
    STATUS_CHOICES = (
        ('reported', 'Reported'),
        ('under_repair', 'Under Repair'),
        ('resolved', 'Resolved'),
    )

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='damage_reports')
    allocation = models.ForeignKey(
        ResourceAllocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='damage_reports'
    )
    quantity_damaged = models.PositiveIntegerField(default=1)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='minor')
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='reported')
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='damage_reports_filed'
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='damage_reports_resolved'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.resource.name}: {self.get_severity_display()} damage ({self.quantity_damaged})"

    def clean(self):
        if self.resource_id and self.quantity_damaged and self.quantity_damaged > self.resource.total_quantity:
            raise ValidationError("Damaged quantity can't exceed the resource's total quantity.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def resolve(self, resolved_by):
        self.status = 'resolved'
        self.resolved_by = resolved_by
        self.resolved_at = timezone.now()
        self.save()
