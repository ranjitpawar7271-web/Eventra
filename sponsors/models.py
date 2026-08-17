from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Sponsor(models.Model):
    """A sponsoring company/organization — the reusable catalog entry.

    This is the "real Sponsor model" flagged as deferred back in Module 6
    (budget/models.py's `RevenueEntry.sponsor_name` free-text field). One
    Sponsor can back multiple events over time via `EventSponsorship`
    below, same relationship shape as `VendorProfile` -> `VendorContract`
    in Module 4.

    Catalog management (create/edit/delete a Sponsor record) is Super
    Admin-only, per the spec's permission note for this module. Browsing
    the catalog is open to anyone who can manage events, so an organizer
    can see who's available to attach to their own event.
    """

    company_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    logo = models.ImageField(upload_to='sponsor_logos/', blank=True, null=True)
    website = models.URLField(blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive sponsors are hidden from the picker when attaching a new sponsorship."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sponsors_created'
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
            while Sponsor.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('sponsors:sponsor_detail', kwargs={'slug': self.slug})

    @property
    def total_confirmed_amount(self):
        """Sum of this sponsor's confirmed/paid sponsorships across all events."""
        total = self.sponsorships.filter(
            status__in=EventSponsorship.CONFIRMED_STATUSES
        ).aggregate(models.Sum('amount'))['amount__sum']
        return total or 0


class EventSponsorship(models.Model):
    """A single sponsorship deal: one Sponsor backing one Event for a
    package/amount. This is the "ad" record the spec's Sponsor
    Advertisement Management asked for.

    Only `confirmed`/`paid` sponsorships count toward budget revenue
    (see `budget.models.EventBudget.sponsorship_total`) — the same
    "don't count it until it's real" rule Module 6 used for expenses and
    Module 4 used for vendor payments, so logging a sponsorship never
    silently inflates an event's numbers before the money is real.
    """

    PACKAGE_CHOICES = (
        ('platinum', 'Platinum'),
        ('gold', 'Gold'),
        ('silver', 'Silver'),
        ('bronze', 'Bronze'),
        ('custom', 'Custom'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    )
    # Statuses that count as real, bankable sponsorship revenue.
    CONFIRMED_STATUSES = ('confirmed', 'paid')

    sponsor = models.ForeignKey(Sponsor, on_delete=models.CASCADE, related_name='sponsorships')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='sponsorships')
    package = models.CharField(max_length=20, choices=PACKAGE_CHOICES, default='custom')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    benefits = models.TextField(
        blank=True,
        help_text="What the sponsor gets in return — logo placement, booth space, mentions, etc."
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sponsorships_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sponsor.company_name} → {self.event.title} ({self.get_package_display()})"

    @property
    def is_confirmed_revenue(self):
        return self.status in self.CONFIRMED_STATUSES
