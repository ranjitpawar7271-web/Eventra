from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from categories.models import Category
from event_management.validators import (
    safe_upload_to, validate_image_contents, validate_image_extension, validate_image_size,
)


class Event(models.Model):
    """A single event that users can browse, manage, and register for."""

    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name='events'
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='organized_events'
    )
    location = models.CharField(
        max_length=255,
        help_text="Free-text venue/location name, used when no registered Venue is selected."
    )
    venue = models.ForeignKey(
        'venues.Venue', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='events',
        help_text="Optional: link to a managed Venue for booking, conflict detection, and capacity checks."
    )
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='events',
        help_text=(
            "Optional: which Organization (tenant) this event belongs to. Nullable and additive — "
            "existing events with no organization are unaffected. See organizations.models.Organization "
            "for the scope of what this field does and does not enforce."
        )
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=50)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    image = models.ImageField(
        upload_to=safe_upload_to('event_images'), blank=True, null=True,
        validators=[validate_image_extension, validate_image_size, validate_image_contents],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('events:event_detail', kwargs={'slug': self.slug})

    def get_registration_qr_url(self):
        """URL of the PNG endpoint that renders this event's registration
        QR code (see events.views.event_registration_qr). The QR itself
        encodes `get_absolute_url()` — the public event detail page,
        which already carries the Register button/form — not a separate
        registration system, so there is exactly one entry point for
        registration whether a participant clicks, types the link, or
        scans the code.
        """
        return reverse('events:event_registration_qr', kwargs={'slug': self.slug})

    @property
    def seats_taken(self):
        return self.registrations.filter(status='confirmed').count()

    @property
    def seats_left(self):
        return max(self.capacity - self.seats_taken, 0)

    @property
    def is_full(self):
        return self.seats_left <= 0

    @property
    def is_upcoming(self):
        return self.start_date >= timezone.now()

    @property
    def is_registration_open(self):
        """True only when this event can still accept *new* registrations
        or waitlist joins: it must be published (not draft, cancelled, or
        completed) and not yet started. Capacity is checked separately
        (a full event still counts as "open" — it routes to the
        waitlist instead). Centralizing this here means every entry
        point (direct register, waitlist join/claim/promote) reads the
        same rule instead of re-implementing — and possibly
        drifting out of sync with — their own version of it.
        """
        return self.status == 'published' and self.start_date > timezone.now()

    @property
    def is_free(self):
        return self.price == 0

    @property
    def has_ended(self):
        return self.end_date < timezone.now()

    @property
    def average_rating(self):
        result = self.reviews.aggregate(avg=models.Avg('rating'))['avg']
        return round(result, 1) if result is not None else None

    @property
    def review_count(self):
        return self.reviews.count()

    @property
    def full_address(self):
        """Best available address string: linked Venue's address+city if
        one is set, otherwise just the free-text `location` field."""
        if self.venue:
            parts = [self.venue.name, self.venue.address, self.venue.city]
            return ", ".join(p for p in parts if p)
        return self.location

    @property
    def map_url(self):
        """A plain Google Maps search link — no paid API key needed, per
        the spec's "don't require a complicated paid map integration"."""
        import urllib.parse
        query = urllib.parse.quote(self.full_address or self.location)
        return f"https://www.google.com/maps/search/?api=1&query={query}"

    @property
    def preparation_progress(self):
        """"Event Preparation Progress" — % of this event's checklist
        (tasks.Task) marked Done. Reuses the existing task board rather
        than a separate checklist model, per that app's own docstring on
        why a checklist is just a degenerate task list. Returns None
        when there are no tasks yet, so templates can show an empty
        state instead of a misleading 0%."""
        total = self.tasks.count()
        if not total:
            return None
        done = self.tasks.filter(status='done').count()
        return round((done / total) * 100)


class Registration(models.Model):
    """Tracks a user's registration for an event."""

    STATUS_CHOICES = (
        ('pending_payment', 'Pending Payment'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='registrations'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')
        ordering = ['-registered_at']

    def __str__(self):
        return f"{self.user} -> {self.event}"


class WaitlistEntry(models.Model):
    """A user waiting for a seat on a full event.

    Reuses the same Event/User pair pattern as `Registration` rather than
    a new app, since a waitlist entry is really "a registration that
    hasn't been confirmed yet because there's no seat" — it lives right
    next to Registration for that reason. Promotion turns this into a
    real `Registration` (see services.promote_next_waitlisted); it never
    grants a seat by itself.
    """

    STATUS_WAITING = 'waiting'
    STATUS_NOTIFIED = 'notified'
    STATUS_EXPIRED = 'expired'
    STATUS_PROMOTED = 'promoted'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_WAITING, 'Waiting'),
        (STATUS_NOTIFIED, 'Notified — pending registration'),
        (STATUS_EXPIRED, 'Invitation Expired'),
        (STATUS_PROMOTED, 'Promoted — registered'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    INVITE_WINDOW_HOURS = 48

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='waitlist_entries')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='waitlist_entries'
    )
    position = models.PositiveIntegerField(
        help_text="1-based queue position among currently active (waiting/notified) entries for this event."
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    joined_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    invitation_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['position', 'joined_at']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user'],
                condition=models.Q(status__in=['waiting', 'notified']),
                name='unique_active_waitlist_entry_per_event_user',
            ),
        ]
        indexes = [models.Index(fields=['event', 'status', 'position'])]

    def __str__(self):
        return f"{self.user} waitlisted for {self.event} (#{self.position})"

    @property
    def is_active(self):
        return self.status in (self.STATUS_WAITING, self.STATUS_NOTIFIED)

    @property
    def invitation_is_expired(self):
        return (
            self.status == self.STATUS_NOTIFIED
            and self.invitation_expires_at is not None
            and timezone.now() > self.invitation_expires_at
        )