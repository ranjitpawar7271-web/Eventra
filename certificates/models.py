import uuid

from django.conf import settings
from django.core import signing
from django.db import models
from django.urls import reverse

# Namespaced the same way tickets.models.QR_SALT is — a certificate token
# can never be replayed as a ticket token or vice versa, since each
# signing.dumps() call is salted for its own purpose.
CERT_SALT = 'certificates.verify'


class Certificate(models.Model):
    """A certificate or digital badge issued for one confirmed, attended
    registration.

    "Certificate Generation with QR Verification" and "Digital Badge
    Generation" are the same underlying artifact — a signed, publicly
    verifiable credential tied to one attendee — so they share one model
    with a `cert_type` distinguishing a full certificate from a smaller
    badge, rather than two parallel tables with duplicated verification
    logic. This mirrors the reasoning already used for Task/Checklist in
    the `tasks` app.

    Deliberately keyed to `Ticket`, not `Registration` directly: a
    certificate is proof of *attendance*, and `Ticket.is_checked_in` is
    the only place that's actually recorded (Module 7). A confirmed
    registration that never checked in gets no certificate — issuing one
    anyway would just be a fake attendance record.
    """

    TYPE_CERTIFICATE = 'certificate'
    TYPE_BADGE = 'badge'
    CERT_TYPE_CHOICES = (
        (TYPE_CERTIFICATE, 'Certificate'),
        (TYPE_BADGE, 'Digital Badge'),
    )
    BADGE_LEVEL_CHOICES = (
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
    )

    ticket = models.OneToOneField(
        'tickets.Ticket', on_delete=models.CASCADE, related_name='certificate'
    )
    cert_type = models.CharField(max_length=15, choices=CERT_TYPE_CHOICES, default=TYPE_CERTIFICATE)
    title = models.CharField(
        max_length=150, default='Certificate of Attendance',
        help_text="Shown on the PDF, e.g. 'Certificate of Attendance', 'Volunteer Badge'."
    )
    badge_level = models.CharField(max_length=10, choices=BADGE_LEVEL_CHOICES, blank=True)
    certificate_code = models.CharField(max_length=24, unique=True, editable=False)
    verify_token = models.TextField(editable=False, blank=True)

    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='certificates_issued'
    )
    revoked = models.BooleanField(
        default=False,
        help_text="A revoked certificate still exists (audit trail) but fails public verification."
    )

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"{self.get_cert_type_display()} for {self.participant} — {self.event.title}"

    # --- Convenience passthroughs, same pattern as tickets.models.Ticket ---
    @property
    def event(self):
        return self.ticket.event

    @property
    def participant(self):
        return self.ticket.participant

    def get_absolute_url(self):
        return reverse('certificates:certificate_detail', kwargs={'certificate_code': self.certificate_code})

    def get_verify_url(self):
        return reverse('certificates:verify', kwargs={'token': self.verify_token})

    # --- Code / token generation, mirroring Ticket._generate_code -------
    @staticmethod
    def _generate_code():
        return f"CERT-{uuid.uuid4().hex[:10].upper()}"

    def _make_verify_token(self):
        return signing.dumps(self.certificate_code, salt=CERT_SALT)

    def save(self, *args, **kwargs):
        if not self.certificate_code:
            code = self._generate_code()
            while Certificate.objects.filter(certificate_code=code).exists():
                code = self._generate_code()
            self.certificate_code = code
        if not self.verify_token:
            self.verify_token = self._make_verify_token()
        super().save(*args, **kwargs)

    @classmethod
    def resolve_token(cls, token):
        """Verify a scanned/visited token and return the matching
        Certificate, or None if the signature is invalid/tampered or no
        certificate matches. Never raises, same contract as
        `Ticket.resolve_token` — a public verification page always needs a
        clean pass/fail, not a stray exception.
        """
        try:
            code = signing.loads(token, salt=CERT_SALT)
        except signing.BadSignature:
            return None
        return cls.objects.filter(certificate_code=code).select_related(
            'ticket__registration__event', 'ticket__registration__user'
        ).first()
