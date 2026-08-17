"""
Module 9 — Workflow, Notifications & Calendar.

Three concerns live in one app because they're small and tightly related:
approvals gate a status change, notifications tell someone about it, and
the calendar is just a read-only view over dates that already exist on
Event/VenueBooking/ShiftAssignment. None of them need their own app.

ApprovalStep is deliberately generic (via ContentType) rather than a
straight FK to Event, matching the spec's "generic-ish model that can
attach to an Event (and later other approvable things)". Today only
Event uses it (the Draft -> Published gate); a future module can reuse
the same model for, say, vendor contract sign-off, without a migration
on this app.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


class WorkflowSettings(models.Model):
    """Singleton, organization-wide workflow configuration.

    A real multi-tenant product would key this per-organization; this
    project only has one organization, so a single row (pk=1) is enough —
    same "one row is the whole config" shape as a typical site-settings
    table, just scoped to workflow instead.
    """

    require_event_approval = models.BooleanField(
        default=False,
        help_text=(
            "If on, an Event moving to Published is held back as Draft "
            "until a Super Admin/Staff member approves it. Off by default "
            "so existing organizer workflows aren't interrupted until "
            "someone deliberately opts in."
        ),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='workflow_settings_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Workflow settings'
        verbose_name_plural = 'Workflow settings'

    def __str__(self):
        return "Workflow settings"

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class ApprovalStep(models.Model):
    """One request to move an approvable object into a pipeline stage.

    The full pipeline the spec lays out is Planning -> Approval ->
    Published -> Registration -> Execution -> Completed -> Archived.
    `stage` records which of those a given request is *for*; the only
    stage anything currently gates on is `published` (see signals.py),
    but the model doesn't hardcode that, so wiring up an approval gate
    for another stage later is a signal, not a migration.
    """

    STAGE_PLANNING = 'planning'
    STAGE_APPROVAL = 'approval'
    STAGE_PUBLISHED = 'published'
    STAGE_REGISTRATION = 'registration'
    STAGE_EXECUTION = 'execution'
    STAGE_COMPLETED = 'completed'
    STAGE_ARCHIVED = 'archived'

    STAGE_CHOICES = (
        (STAGE_PLANNING, 'Planning'),
        (STAGE_APPROVAL, 'Approval'),
        (STAGE_PUBLISHED, 'Published'),
        (STAGE_REGISTRATION, 'Registration'),
        (STAGE_EXECUTION, 'Execution'),
        (STAGE_COMPLETED, 'Completed'),
        (STAGE_ARCHIVED, 'Archived'),
    )

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default=STAGE_APPROVAL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    comment = models.TextField(blank=True, help_text="Approver's note, especially for a rejection.")

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approval_steps_requested'
    )
    requested_at = models.DateTimeField(auto_now_add=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approval_steps_decided'
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
        indexes = [models.Index(fields=['content_type', 'object_id'])]

    def __str__(self):
        return f"{self.get_stage_display()} approval for {self.content_object} ({self.get_status_display()})"

    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING

    def approve(self, user, comment=''):
        self.status = self.STATUS_APPROVED
        self.decided_by = user
        self.decided_at = timezone.now()
        self.comment = comment
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'comment'])
        self._apply_to_target()
        return self

    def reject(self, user, comment=''):
        self.status = self.STATUS_REJECTED
        self.decided_by = user
        self.decided_at = timezone.now()
        self.comment = comment
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'comment'])
        self._notify_decision()
        return self

    def _apply_to_target(self):
        """Push an approval through to the thing it was gating.

        Only Event/`published` is wired up today. Setting the field
        through the model (not `.update()`) deliberately re-runs the
        Event pre_save/post_save signals in signals.py — with this step
        now approved, the gate finds it and lets the status through
        instead of bouncing it back to Draft again.
        """
        target = self.content_object
        from events.models import Event
        if isinstance(target, Event) and self.stage == self.STAGE_PUBLISHED:
            target.status = 'published'
            target.save(update_fields=['status'])
        self._notify_decision()

    def _notify_decision(self):
        target = self.content_object
        title = getattr(target, 'title', str(target))
        requester = self.requested_by
        if not requester:
            return
        if self.status == self.STATUS_APPROVED:
            message = f"'{title}' was approved and is now live."
        else:
            reason = f" Reason: {self.comment}" if self.comment else ""
            message = f"'{title}' was not approved to publish.{reason}"
        link = getattr(target, 'get_absolute_url', lambda: '')()
        Notification.notify(
            requester, message, link=link, notification_type=Notification.TYPE_APPROVAL,
            dedupe_key=f'approval-decided-{self.pk}',
        )


class Notification(models.Model):
    """An in-app notification for one user, optionally also emailed.

    `dedupe_key` lets a scheduled rule (see management/commands/
    send_reminders.py) be re-run safely — running it twice for the same
    event/user/rule combination is a no-op instead of spamming a second
    copy, enforced by the unique_together below. Ad-hoc notifications
    (an approval decision, a fresh staff assignment) leave it null,
    which unique_together treats as distinct every time, so those are
    never accidentally deduped against each other.
    """

    TYPE_APPROVAL = 'approval'
    TYPE_REMINDER = 'reminder'
    TYPE_STAFF = 'staff'
    TYPE_VENDOR = 'vendor'
    TYPE_PAYMENT = 'payment'
    TYPE_ANNOUNCEMENT = 'announcement'
    TYPE_SYSTEM = 'system'
    TYPE_REGISTRATION = 'registration'
    TYPE_TICKET = 'ticket'
    TYPE_CERTIFICATE = 'certificate'
    TYPE_CHECKIN = 'checkin'
    TYPE_CAPACITY = 'capacity'
    TYPE_BUDGET = 'budget'
    TYPE_TASK = 'task'
    TYPE_EVENT_CANCELLED = 'event_cancelled'
    TYPE_EVENT_RESCHEDULED = 'event_rescheduled'

    TYPE_CHOICES = (
        (TYPE_APPROVAL, 'Approval'),
        (TYPE_REMINDER, 'Reminder'),
        (TYPE_STAFF, 'Staff'),
        (TYPE_VENDOR, 'Vendor'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_ANNOUNCEMENT, 'Announcement'),
        (TYPE_SYSTEM, 'System'),
        (TYPE_REGISTRATION, 'Registration'),
        (TYPE_TICKET, 'Ticket'),
        (TYPE_CERTIFICATE, 'Certificate'),
        (TYPE_CHECKIN, 'Check-in'),
        (TYPE_CAPACITY, 'Capacity Warning'),
        (TYPE_BUDGET, 'Budget Warning'),
        (TYPE_TASK, 'Task Deadline'),
        (TYPE_EVENT_CANCELLED, 'Event Cancelled'),
        (TYPE_EVENT_RESCHEDULED, 'Event Rescheduled'),
    )

    TYPE_ICONS = {
        TYPE_APPROVAL: 'bi-clipboard-check',
        TYPE_REMINDER: 'bi-alarm',
        TYPE_STAFF: 'bi-person-badge',
        TYPE_VENDOR: 'bi-truck',
        TYPE_PAYMENT: 'bi-cash-coin',
        TYPE_ANNOUNCEMENT: 'bi-megaphone',
        TYPE_SYSTEM: 'bi-info-circle',
        TYPE_REGISTRATION: 'bi-ticket-perforated',
        TYPE_TICKET: 'bi-qr-code',
        TYPE_CERTIFICATE: 'bi-award',
        TYPE_CHECKIN: 'bi-check-circle',
        TYPE_CAPACITY: 'bi-exclamation-triangle',
        TYPE_BUDGET: 'bi-wallet2',
        TYPE_TASK: 'bi-list-check',
        TYPE_EVENT_CANCELLED: 'bi-x-octagon',
        TYPE_EVENT_RESCHEDULED: 'bi-calendar-event',
    }

    PRIORITY_LOW = 'low'
    PRIORITY_NORMAL = 'normal'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    PRIORITY_CHOICES = (
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_NORMAL, 'Normal'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True, help_text="In-app URL this notification points to.")
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_SYSTEM)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    related_event = models.ForeignKey(
        'events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications',
        help_text="The event this notification is about, where applicable — lets the UI group/filter by event."
    )
    is_read = models.BooleanField(default=False)
    dedupe_key = models.CharField(
        max_length=140, null=True, blank=True,
        help_text="Set by scheduled rules so re-running send_reminders doesn't duplicate this notification."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'dedupe_key')
        indexes = [models.Index(fields=['user', 'is_read'])]

    def __str__(self):
        return f"{self.user}: {self.message[:50]}"

    @property
    def icon(self):
        return self.TYPE_ICONS.get(self.notification_type, 'bi-bell')

    @classmethod
    def notify(cls, user, message, link='', notification_type=TYPE_SYSTEM, dedupe_key=None, email=True,
               priority=PRIORITY_NORMAL, related_event=None):
        """Create a notification, skipping it if `dedupe_key` already
        fired for this user. Returns the Notification, or None if it was
        a duplicate that got skipped.
        """
        if dedupe_key:
            existing = cls.objects.filter(user=user, dedupe_key=dedupe_key).first()
            if existing:
                return None

        notification = cls.objects.create(
            user=user, message=message, link=link,
            notification_type=notification_type, dedupe_key=dedupe_key,
            priority=priority, related_event=related_event,
        )

        if email and user.email:
            try:
                send_mail(
                    subject=f"Eventra: {message[:78]}",
                    message=message,
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                # Console/dev email backends practically never raise, but a
                # notification is still worth keeping even if email delivery
                # fails for some other backend in production.
                pass

        return notification
