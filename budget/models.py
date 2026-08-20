from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from event_management.validators import (
    safe_upload_to, validate_document_extension, validate_document_size,
)


class EventBudget(models.Model):
    """The financial anchor for a single Event — one-to-one, same pattern
    as VendorContract hanging off Vendor in Module 4.

    Everything else in this app (Expense, RevenueEntry) rolls up to this
    row. `total_expenses`, `total_revenue`, and `profit_or_loss` are never
    stored — they're computed live from the related rows (and from
    Module 4's VendorPayment), the same "derive it live" approach used for
    `VendorContract.balance_due`, so these numbers can't drift out of sync
    with the underlying records.
    """

    # Only expenses in one of these statuses count toward "actual" spend.
    # A `pending` expense has been logged but isn't final yet, so it must
    # not silently move the budget-vs-actual numbers until someone
    # approves (or pays) it.
    CONFIRMED_EXPENSE_STATUSES = ('approved', 'paid')

    event = models.OneToOneField(
        'events.Event', on_delete=models.CASCADE, related_name='budget'
    )
    estimated_budget = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="What this event is expected to cost, set at planning time."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='budgets_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Budget for {self.event.title}"

    def get_absolute_url(self):
        return reverse('budget:budget_detail', kwargs={'event_slug': self.event.slug})

    # --- Expenses --------------------------------------------------
    @property
    def direct_expenses_total(self):
        """Sum of this event's own Expense rows that are approved/paid."""
        total = self.expenses.filter(
            status__in=self.CONFIRMED_EXPENSE_STATUSES
        ).aggregate(models.Sum('amount'))['amount__sum']
        return total or 0

    @property
    def vendor_payments_total(self):
        """Paid VendorPayments against this event's vendor contracts.

        Reuses Module 4's VendorPayment instead of duplicating a payments
        table here — a vendor payment already *is* an expense, so
        double-tracking it separately would let the two numbers drift
        apart. Only `paid` payments count, matching the same "don't count
        it until it's actually paid" rule VendorContract.balance_due uses.
        """
        from vendors.models import VendorPayment
        total = VendorPayment.objects.filter(
            contract__event=self.event, status='paid'
        ).aggregate(models.Sum('amount'))['amount__sum']
        return total or 0

    @property
    def total_expenses(self):
        return self.direct_expenses_total + self.vendor_payments_total

    # --- Revenue -----------------------------------------------------
    @property
    def sponsorship_deals_total(self):
        """Confirmed/paid EventSponsorship amounts for this event (Module 10).

        Same reuse pattern as `vendor_payments_total` above: a real
        Sponsor-linked deal already *is* revenue, so it isn't also typed
        in as a manual RevenueEntry. The older `RevenueEntry(source=
        'sponsorship')` free-text path from Module 6 still works exactly
        as before for anyone who logged sponsorship income that way
        before a real Sponsor record existed for it — nothing here
        removes or double-counts those rows.
        """
        from sponsors.models import EventSponsorship
        total = EventSponsorship.objects.filter(
            event=self.event, status__in=EventSponsorship.CONFIRMED_STATUSES
        ).aggregate(models.Sum('amount'))['amount__sum']
        return total or 0

    @property
    def ticket_sales_total(self):
        """Successful ticket-purchase Payments for this event (Phase 3's
        payments app). Same reuse pattern as `sponsorship_deals_total`
        above — a paid registration already *is* revenue, so it isn't
        also hand-entered as a RevenueEntry. Only `successful` payments
        count; a refunded payment's `Payment.status` moves to `refunded`
        so it naturally drops out of this sum without needing a separate
        subtraction step.
        """
        from payments.models import Payment
        total = Payment.objects.filter(
            event=self.event, status=Payment.STATUS_SUCCESSFUL
        ).aggregate(models.Sum('amount'))['amount__sum']
        return total or 0

    @property
    def total_revenue(self):
        total = self.revenue_entries.aggregate(models.Sum('amount'))['amount__sum']
        return (total or 0) + self.sponsorship_deals_total + self.ticket_sales_total

    # --- Profit / loss & variance ------------------------------------
    @property
    def profit_or_loss(self):
        return self.total_revenue - self.total_expenses

    @property
    def is_profitable(self):
        return self.profit_or_loss >= 0

    @property
    def variance(self):
        """estimated_budget - total_expenses. Positive = under budget,
        negative = over budget."""
        return self.estimated_budget - self.total_expenses

    @property
    def is_over_budget(self):
        return self.variance < 0

    @property
    def variance_abs(self):
        return abs(self.variance)

    @property
    def percent_spent(self):
        if not self.estimated_budget:
            return None
        return round((self.total_expenses / self.estimated_budget) * 100, 1)

    # --- Category breakdown --------------------------------------------
    @property
    def category_breakdown(self):
        """Confirmed (approved/paid) expenses grouped by category, plus a
        synthetic 'Vendor Payments' row so vendor spend isn't invisible
        here even though VendorPayment has no category of its own. This
        is the data Module 8's Expense/Budget Reports will chart.
        """
        rows = []
        totals = dict(
            self.expenses.filter(status__in=self.CONFIRMED_EXPENSE_STATUSES)
            .values_list('category')
            .annotate(total=models.Sum('amount'))
            .values_list('category', 'total')
        )
        for code, label in Expense.CATEGORY_CHOICES:
            rows.append({'code': code, 'label': label, 'total': totals.get(code, 0) or 0})

        vendor_total = self.vendor_payments_total
        if vendor_total:
            rows.append({'code': 'vendor_payments', 'label': 'Vendor Payments', 'total': vendor_total})
        return rows

    @property
    def revenue_breakdown(self):
        """Revenue grouped by source, mirroring `category_breakdown`'s shape
        but for income instead of spend: manual RevenueEntry rows grouped
        by their `source` choice, plus a synthetic 'Sponsorship Deals' row
        for confirmed/paid EventSponsorship amounts (Module 10).
        """
        rows = []
        totals = dict(
            self.revenue_entries.values_list('source')
            .annotate(total=models.Sum('amount'))
            .values_list('source', 'total')
        )
        for code, label in RevenueEntry.SOURCE_CHOICES:
            rows.append({'code': code, 'label': label, 'total': totals.get(code, 0) or 0})

        sponsorship_total = self.sponsorship_deals_total
        if sponsorship_total:
            rows.append({'code': 'sponsorship_deals', 'label': 'Sponsorship Deals', 'total': sponsorship_total})
        return rows


class Expense(models.Model):
    """A single line-item cost against an EventBudget."""

    CATEGORY_CHOICES = (
        ('venue', 'Venue'),
        ('catering', 'Catering'),
        ('marketing', 'Marketing'),
        ('staff', 'Staff'),
        ('equipment', 'Equipment'),
        ('travel', 'Travel'),
        ('miscellaneous', 'Miscellaneous'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    )

    budget = models.ForeignKey(EventBudget, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='miscellaneous')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    receipt = models.FileField(
        upload_to=safe_upload_to('expense_receipts'), blank=True, null=True,
        validators=[validate_document_extension, validate_document_size],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses_recorded'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_category_display()}: ₹{self.amount} ({self.budget.event.title})"


class RevenueEntry(models.Model):
    """Money coming in for an event: ticket sales, sponsorship, or a
    manual catch-all entry.

    `ticket_sales` entries are manual for now — Module 7 (Ticketing) will
    add automatic entries pulled from Registration/ticket data once that
    model exists, without changing this schema. `sponsorship` carries a
    free-text `sponsor_name` for the same reason: it'll become a FK to a
    Sponsor model once one exists, but doesn't need to block this module.
    """

    SOURCE_CHOICES = (
        ('ticket_sales', 'Ticket Sales'),
        ('sponsorship', 'Sponsorship'),
        ('other', 'Other / Manual'),
    )

    budget = models.ForeignKey(EventBudget, on_delete=models.CASCADE, related_name='revenue_entries')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='other')
    sponsor_name = models.CharField(
        max_length=200, blank=True,
        help_text="Only used when source is Sponsorship. Will become a link to a Sponsor model later."
    )
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='revenue_entries_recorded'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'Revenue entries'

    def __str__(self):
        return f"{self.get_source_display()}: ₹{self.amount} ({self.budget.event.title})"

    def clean(self):
        if self.source == 'sponsorship' and not self.sponsor_name:
            raise ValidationError({'sponsor_name': "Sponsor name is required for sponsorship income."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
