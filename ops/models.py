from django.conf import settings
from django.db import models


class BackupLog(models.Model):
    """An audit trail entry for every backup/restore attempt — including
    failed restores. Ops tooling that lets someone overwrite live data
    needs a record of who did it, when, and whether it actually worked,
    not just the action itself."""

    ACTION_BACKUP = 'backup'
    ACTION_RESTORE = 'restore'
    ACTION_CHOICES = (
        (ACTION_BACKUP, 'Backup'),
        (ACTION_RESTORE, 'Restore'),
    )
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    )

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    filename = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True, help_text="Object count on success, or the error message on failure.")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='backup_actions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} ({self.get_status_display()}) at {self.created_at}"
