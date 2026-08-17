from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]


class Review(models.Model):
    """A participant's 1-5 star review of an event, submitted after they
    attended/the event completed (enforced in views._can_review, not here
    — the model itself doesn't need to know about check-in/completion
    rules to stay a clean data record).

    `unique_together` is the only defense against a second review from
    the same user for the same event, matching how `events.Registration`
    prevents double-registration the same way.
    """

    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_reviews')

    rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS, help_text="Overall rating, 1-5 stars.")
    venue_rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS, null=True, blank=True)
    organization_rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS, null=True, blank=True)
    comment = models.TextField(blank=True, max_length=2000)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['event', 'user'], name='one_review_per_user_per_event'),
        ]
        indexes = [models.Index(fields=['event', 'rating'])]

    def __str__(self):
        return f"{self.user} rated {self.event} {self.rating}/5"
