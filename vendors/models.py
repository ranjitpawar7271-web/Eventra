from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg
from django.urls import reverse
from django.utils.text import slugify

from event_management.validators import (
    safe_upload_to,
    validate_document_extension,
    validate_document_size,
    validate_image_contents,
    validate_image_extension,
    validate_image_size,
)


class VendorProfile(models.Model):
    """The business profile for a user with role=vendor.

    One-to-one with User: a vendor account and its business profile are
    the same thing, kept separate from User so vendor-specific fields
    don't bloat the core user model.
    """

    SERVICE_TYPE_CHOICES = (
        ('catering', 'Catering'),
        ('decoration', 'Decoration'),
        ('photography', 'Photography & Videography'),
        ('security', 'Security'),
        ('transport', 'Transport'),
        ('sound_lighting', 'Sound & Lighting'),
        ('printing', 'Printing & Branding'),
        ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vendor_profile')
    company_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPE_CHOICES, default='other')
    contact_person = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(
        upload_to=safe_upload_to('vendor_logos'), blank=True, null=True,
        validators=[validate_image_extension, validate_image_size, validate_image_contents],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendor_profiles_reviewed'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_name']

    def __str__(self):
        return self.company_name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.company_name)
            slug = base_slug
            counter = 1
            while VendorProfile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('vendors:vendor_detail', kwargs={'slug': self.slug})

    @property
    def is_approved(self):
        return self.status == 'approved'

    # --- Performance tracking ---------------------------------------
    @property
    def avg_service_quality(self):
        return self.ratings.aggregate(v=Avg('service_quality'))['v']

    @property
    def avg_delivery_time(self):
        return self.ratings.aggregate(v=Avg('delivery_time'))['v']

    @property
    def performance_score(self):
        """Overall score out of 5: average of service quality + delivery time."""
        quality = self.avg_service_quality
        delivery = self.avg_delivery_time
        if quality is None or delivery is None:
            return None
        return round((quality + delivery) / 2, 2)

    @property
    def rating_count(self):
        return self.ratings.count()


class VendorService(models.Model):
    """A service/offering a vendor lists on their profile."""

    PRICE_UNIT_CHOICES = (
        ('flat', 'Flat rate'),
        ('per_hour', 'Per hour'),
        ('per_day', 'Per day'),
        ('per_person', 'Per person'),
        ('per_event', 'Per event'),
    )

    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_unit = models.CharField(max_length=20, choices=PRICE_UNIT_CHOICES, default='flat')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} — {self.vendor.company_name}"


class VendorDocument(models.Model):
    """Contracts, licenses, certifications, insurance proof, etc."""

    DOCUMENT_TYPE_CHOICES = (
        ('license', 'Business License'),
        ('certification', 'Certification'),
        ('insurance', 'Insurance Proof'),
        ('contract', 'Contract'),
        ('other', 'Other'),
    )

    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='other')
    file = models.FileField(
        upload_to=safe_upload_to('vendor_documents'),
        validators=[validate_document_extension, validate_document_size],
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} ({self.vendor.company_name})"


class VendorContract(models.Model):
    """An agreement between the platform/an organizer and a vendor,
    optionally tied to a specific event."""

    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('signed', 'Signed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='contracts')
    event = models.ForeignKey(
        'events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_contracts'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    document = models.FileField(
        upload_to=safe_upload_to('vendor_contracts'), blank=True, null=True,
        validators=[validate_document_extension, validate_document_size],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_contracts_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.vendor.company_name}"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be before the start date.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def total_paid(self):
        return self.payments.filter(status='paid').aggregate(models.Sum('amount'))['amount__sum'] or 0

    @property
    def balance_due(self):
        return self.amount - self.total_paid


class VendorRating(models.Model):
    """Post-event performance feedback for a vendor."""

    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='ratings')
    event = models.ForeignKey(
        'events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_ratings'
    )
    rated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    service_quality = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    delivery_time = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor.company_name}: {self.service_quality}/5 quality, {self.delivery_time}/5 delivery"

    @property
    def average(self):
        return round((self.service_quality + self.delivery_time) / 2, 2)


class VendorPayment(models.Model):
    """A payment made to a vendor, optionally against a contract."""

    METHOD_CHOICES = (
        ('bank_transfer', 'Bank Transfer'),
        ('upi', 'UPI'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    )

    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='payments')
    contract = models.ForeignKey(
        VendorContract, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='bank_transfer')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference_note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    payment_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.amount} to {self.vendor.company_name} ({self.get_status_display()})"
