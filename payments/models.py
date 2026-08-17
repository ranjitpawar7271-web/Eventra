import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """One payment attempt tied to a single event Registration.

    This is a MOCK payment layer — no real gateway is wired in, and no
    real card/bank details are ever collected or stored (see
    `payments/views.py::checkout`, which only takes a method choice).
    That keeps this safe to demo without exposing real payment
    credentials, per the "do not expose real payment credentials"
    requirement. Swapping in a real gateway later only touches
    `payments/services.py::process_mock_payment` — models/views/URLs
    don't need to change.

    One registration can have multiple Payment rows over time (a failed
    attempt followed by a retry), but only ever one that's currently
    'pending' or 'successful' — enforced in services.py rather than a DB
    constraint, since a failed/refunded historical row must stay.
    """

    METHOD_CARD = 'card'
    METHOD_UPI = 'upi'
    METHOD_NETBANKING = 'netbanking'
    METHOD_WALLET = 'wallet'
    METHOD_CHOICES = (
        (METHOD_CARD, 'Credit / Debit Card'),
        (METHOD_UPI, 'UPI'),
        (METHOD_NETBANKING, 'Net Banking'),
        (METHOD_WALLET, 'Wallet'),
    )

    STATUS_PENDING = 'pending'
    STATUS_SUCCESSFUL = 'successful'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESSFUL, 'Successful'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    REFUND_NONE = 'none'
    REFUND_REQUESTED = 'requested'
    REFUND_PROCESSED = 'processed'
    REFUND_STATUS_CHOICES = (
        (REFUND_NONE, 'No Refund'),
        (REFUND_REQUESTED, 'Refund Requested'),
        (REFUND_PROCESSED, 'Refund Processed'),
    )

    registration = models.ForeignKey(
        'events.Registration', on_delete=models.CASCADE, related_name='payments'
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='payments')

    transaction_id = models.CharField(max_length=40, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=15, choices=METHOD_CHOICES, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)

    payment_date = models.DateTimeField(null=True, blank=True, help_text="Set when the gateway returns a final result (success or failure).")
    failure_reason = models.CharField(max_length=255, blank=True)

    refund_status = models.CharField(max_length=15, choices=REFUND_STATUS_CHOICES, default=REFUND_NONE)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status']), models.Index(fields=['event', 'status'])]

    def __str__(self):
        return f"{self.transaction_id} — {self.get_status_display()} (₹{self.amount})"

    @staticmethod
    def _generate_transaction_id():
        return f"TXN-{uuid.uuid4().hex[:14].upper()}"

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            txn = self._generate_transaction_id()
            while Payment.objects.filter(transaction_id=txn).exists():
                txn = self._generate_transaction_id()
            self.transaction_id = txn
        super().save(*args, **kwargs)

    @property
    def is_successful(self):
        return self.status == self.STATUS_SUCCESSFUL

    def mark_successful(self, method):
        self.payment_method = method
        self.status = self.STATUS_SUCCESSFUL
        self.payment_date = timezone.now()
        self.failure_reason = ''
        self.save(update_fields=['payment_method', 'status', 'payment_date', 'failure_reason', 'updated_at'])

    def mark_failed(self, method, reason):
        self.payment_method = method
        self.status = self.STATUS_FAILED
        self.payment_date = timezone.now()
        self.failure_reason = reason
        self.save(update_fields=['payment_method', 'status', 'payment_date', 'failure_reason', 'updated_at'])

    def mark_refunded(self, amount=None):
        self.status = self.STATUS_REFUNDED
        self.refund_status = self.REFUND_PROCESSED
        self.refund_amount = amount if amount is not None else self.amount
        self.refunded_at = timezone.now()
        self.save(update_fields=['status', 'refund_status', 'refund_amount', 'refunded_at', 'updated_at'])
