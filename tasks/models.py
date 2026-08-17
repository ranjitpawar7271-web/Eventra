from django.conf import settings
from django.db import models


class Task(models.Model):
    """A single card on an event's Kanban board.

    This one model covers three separate spec line-items at once: "Task
    Management (Trello-style)" is the board itself; "Event Checklist" is
    just this same board used with short, undated, unassigned cards (a
    checklist is a degenerate case of a task list, not a different data
    shape); "Team Collaboration" is `TaskComment` below plus the
    `assigned_to` field. Treating these as one app avoids three near-
    identical models that would all need the same permission checks.

    "Event Timeline" is intentionally NOT folded in here — a timeline is a
    chronological view of dated milestones, which is really a different
    read/report over Event + Task + other modules' dated records (venue
    booking dates, ticket sale windows, etc.), not another place to store
    data. It's a reporting view to add later, not a model of its own.
    """

    STATUS_CHOICES = (
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('review', 'In Review'),
        ('done', 'Done'),
    )
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )

    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_tasks'
    )
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tasks_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', '-priority', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.event.title})"

    @property
    def is_overdue(self):
        from django.utils import timezone
        return bool(self.due_date) and self.due_date < timezone.now().date() and self.status != 'done'


class TaskComment(models.Model):
    """A comment thread on a task — the "Team Collaboration" half of this
    module. Anyone who can see the board (a manager, or the assignee) can
    leave a comment; see `tasks/views.py::_can_touch_task`.
    """

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_comments')
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on {self.task.title}"
