from django.conf import settings
from django.db import models


class ChatMessage(models.Model):
    """One turn of the Eventra Assistant conversation.

    The on-screen conversation itself lives in the browser (JS array) —
    this table exists for two things the client can't do: rate-limiting
    (counting a user's recent messages) and an audit trail of what the
    assistant told people, without which "the AI must not hallucinate"
    would be unverifiable after the fact. Content is trimmed to keep rows
    small; this is a log, not a transcript store.
    """

    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_CHOICES = ((ROLE_USER, 'User'), (ROLE_ASSISTANT, 'Assistant'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chatbot_messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField(max_length=2000)
    intent = models.CharField(max_length=40, blank=True, help_text="Classified intent, for debugging/audit only.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'created_at'])]

    def __str__(self):
        return f"{self.user} [{self.role}]: {self.content[:40]}"
