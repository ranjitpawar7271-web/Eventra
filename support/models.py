from django.conf import settings
from django.db import models


class FAQItem(models.Model):
    """One entry on the Help Center / FAQ page. Platform-wide, not
    per-event — event-specific Q&A already has a home (Chat/
    Announcements in the `chat` app; Feedback Forms in `surveys`)."""

    question = models.CharField(max_length=300)
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='faq_items_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'order', 'id']

    def __str__(self):
        return self.question


class PlatformAnnouncement(models.Model):
    """A site-wide announcement (Announcement Board) — distinct from
    `chat.Message(message_type='announcement')`, which is scoped to one
    event's audience. This one is platform-wide, so it's a separate
    model rather than an event=None special case bolted onto the
    per-event feed."""

    title = models.CharField(max_length=200)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='platform_announcements_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SupportRequest(models.Model):
    """"Contact Support" and "User Feedback Module" are the same shape —
    someone submitting a message to be triaged by Staff/Super Admin —
    differing only in `request_type`, so they share one model and one
    inbox rather than two parallel systems. This is platform-level
    feedback/support (account issues, bug reports, general suggestions);
    event-specific feedback already has a purpose-built home in the
    `surveys` app (Feedback Forms), which collects structured,
    per-event responses rather than free-form messages.
    """

    TYPE_SUPPORT = 'support'
    TYPE_FEEDBACK = 'feedback'
    REQUEST_TYPE_CHOICES = (
        (TYPE_SUPPORT, 'Support Request'),
        (TYPE_FEEDBACK, 'Feedback / Suggestion'),
    )
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CHOICES = (
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_RESOLVED, 'Resolved'),
    )

    # Submitter isn't required to be logged in — contact/support forms
    # conventionally work for anonymous visitors too — so `user` is
    # optional and name/email are always captured directly.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='support_requests'
    )
    name = models.CharField(max_length=150)
    email = models.EmailField()
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES, default=TYPE_SUPPORT)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='support_requests_resolved'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_request_type_display()}] {self.subject}"
