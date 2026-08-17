import uuid

from django.conf import settings
from django.core import signing
from django.db import models
from django.urls import reverse
from django.utils import timezone

# Salt namespaces the signed QR payload so it can never be confused with a
# token minted for something else in the project (or replayed against a
# different `signing.dumps()` call elsewhere in the codebase).
QR_SALT = 'tickets.qr_checkin'


class Ticket(models.Model):
    """One ticket per confirmed `Registration` (Module 1/events app).

    A Ticket is never created directly by a user — it's issued automatically
    by the `post_save` signal on `Registration` (see signals.py) the moment
    a registration becomes `confirmed`, matching the "no new manual step"
    requirement from the spec. The QR payload is a signed token (Django's
    `signing` module), not the raw ticket id/code, so a ticket can't be
    cloned by guessing or incrementing a number in the URL.
    """

    TYPE_FREE = 'free'
    TYPE_PAID = 'paid'
    TYPE_VIP = 'vip'
    TICKET_TYPE_CHOICES = (
        (TYPE_FREE, 'Free'),
        (TYPE_PAID, 'Paid'),
        (TYPE_VIP, 'VIP'),
    )

    STATUS_ISSUED = 'issued'
    STATUS_CHECKED_IN = 'checked_in'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REFUNDED = 'refunded'
    STATUS_CHOICES = (
        (STATUS_ISSUED, 'Issued'),
        (STATUS_CHECKED_IN, 'Checked In'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_REFUNDED, 'Refunded'),
    )

    registration = models.OneToOneField(
        'events.Registration', on_delete=models.CASCADE, related_name='ticket'
    )
    ticket_code = models.CharField(max_length=20, unique=True, editable=False)
    ticket_type = models.CharField(max_length=10, choices=TICKET_TYPE_CHOICES, default=TYPE_FREE)
    qr_token = models.TextField(
        editable=False, blank=True,
        help_text="Signed payload (django.core.signing) encoded into the QR image. "
                   "Verifying it re-checks the signature, so a forged/edited token is rejected."
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ISSUED)

    issued_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets_checked_in'
    )
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets_checked_out'
    )

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"{self.ticket_code} ({self.registration.event.title})"

    # --- Convenience passthroughs to the registration ------------------
    @property
    def event(self):
        return self.registration.event

    @property
    def event_id(self):
        """Real Django FKs auto-generate `<field>_id`; `event` here is only
        a Python @property (it's on `registration`, not `Ticket` directly),
        so that shadow attribute never existed — `ticket.event_id` raised
        AttributeError. This makes the natural-looking accessor actually
        work, so callers don't have to know `event` is a passthrough.
        """
        return self.registration.event_id

    @property
    def participant(self):
        return self.registration.user

    @property
    def is_checked_in(self):
        return self.status == self.STATUS_CHECKED_IN

    @property
    def is_usable(self):
        """Whether this ticket can still be scanned for entry at all."""
        return self.status in (self.STATUS_ISSUED, self.STATUS_CHECKED_IN)

    def get_absolute_url(self):
        return reverse('tickets:ticket_detail', kwargs={'ticket_code': self.ticket_code})

    # --- Code / token generation ----------------------------------------
    @staticmethod
    def _generate_code():
        # Short, human-readable-enough code staff can also read off a
        # printed ticket if the scanner is unavailable. Not itself a
        # security boundary — the signed qr_token is what prevents forgery.
        return f"EVS-{uuid.uuid4().hex[:10].upper()}"

    def _make_qr_token(self):
        return signing.dumps(self.ticket_code, salt=QR_SALT)

    def save(self, *args, **kwargs):
        if not self.ticket_code:
            code = self._generate_code()
            while Ticket.objects.filter(ticket_code=code).exists():
                code = self._generate_code()
            self.ticket_code = code
        if not self.qr_token:
            self.qr_token = self._make_qr_token()
        super().save(*args, **kwargs)

    @classmethod
    def resolve_token(cls, token):
        """Verify a scanned QR token and return the matching Ticket, or
        None if the signature is invalid/tampered or no ticket matches.

        Never raises — scan handling always needs a clean pass/fail rather
        than a stray exception bubbling out of an AJAX endpoint.
        """
        try:
            code = signing.loads(token, salt=QR_SALT)
        except signing.BadSignature:
            return None
        return cls.objects.filter(ticket_code=code).select_related(
            'registration', 'registration__event', 'registration__user'
        ).first()


class CheckInLog(models.Model):
    """Every scan attempt at the door — successful or not.

    Failed/duplicate attempts are kept as real rows (never silently
    dropped) so "Duplicate Scan Prevention" and "Attendance Reports" stay
    auditable after the fact. `event` is stored directly (not just derived
    through `ticket`) because an invalid/forged scan may not resolve to a
    ticket at all, and we still want a record of where it was attempted.
    """

    RESULT_CHECKED_IN = 'checked_in'
    RESULT_CHECKED_OUT = 'checked_out'
    RESULT_DUPLICATE = 'duplicate_rejected'
    RESULT_INVALID = 'invalid'
    RESULT_CHOICES = (
        (RESULT_CHECKED_IN, 'Checked In'),
        (RESULT_CHECKED_OUT, 'Checked Out'),
        (RESULT_DUPLICATE, 'Duplicate Scan Rejected'),
        (RESULT_INVALID, 'Invalid'),
    )

    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='checkin_logs')
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name='checkin_logs', null=True, blank=True,
        help_text="Blank when the scanned token didn't resolve to any ticket at all."
    )
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checkin_scans'
    )
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    detail = models.CharField(
        max_length=255, blank=True,
        help_text="Human-readable context, e.g. 'Already checked in at 6:04 PM by J. Rao'."
    )
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        who = self.ticket.ticket_code if self.ticket else 'unresolved token'
        return f"{self.get_result_display()} — {who} @ {self.scanned_at:%Y-%m-%d %H:%M}"
