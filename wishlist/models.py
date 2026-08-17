from django.conf import settings
from django.db import models


class FavoriteEvent(models.Model):
    """A user bookmarking/favoriting an event — the spec's "Wishlist" and
    "Event Bookmarking" items are the same underlying feature (a user↔event
    many-to-many with a timestamp), so they're implemented as one model
    rather than two.

    Deliberately open to every role, not just Participants — an Organizer
    or Staff member might want to bookmark another organizer's event too
    (to attend it, track it, etc.), and there's no reason to gate that.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_events'
    )
    event = models.ForeignKey(
        'events.Event', on_delete=models.CASCADE, related_name='favorited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'event'], name='unique_user_event_favorite')
        ]

    def __str__(self):
        return f"{self.user.username} ♥ {self.event.title}"
