from django.conf import settings
from django.db import models


class Photo(models.Model):
    """One photo in an event's gallery. "Event Highlights" isn't a
    separate model — it's the same gallery filtered to `is_highlight=True`,
    a curation flag a manager sets on photos already uploaded, rather than
    a second place to store images.

    Viewing the gallery is public (matches `events.views.event_detail`,
    which has no `@login_required` — event pages are browsable by anyone).
    Uploading is restricted to that event's actual audience: crowd-sourced
    photos from people who were actually there, not open upload from
    anyone with an account. See `_can_upload` in views.py.
    """

    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='event_gallery/')
    caption = models.CharField(max_length=200, blank=True)
    is_highlight = models.BooleanField(
        default=False,
        help_text="Curated by a manager — shown in the 'Highlights' filter."
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_photos'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Photo for {self.event.title} by {self.uploaded_by}"
