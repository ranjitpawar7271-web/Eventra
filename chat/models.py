from django.conf import settings
from django.db import models


class Message(models.Model):
    """One message in an event's feed. "Event Chat Room" and "Live Event
    Announcements" are the same underlying feed viewed by the same
    audience — the only real difference is who's allowed to post and how
    it's styled, so both are `message_type` on one model rather than two
    separate feeds a client would have to poll and merge separately.

    Polling-based, not websockets: the module plan explicitly flagged
    that live chat/announcements would need Django Channels (a new
    dependency) for a true push feed, and defaulted to polling absent a
    request for that infrastructure. `chat/views.py::message_poll`
    returns any messages newer than a given id; the page's JS calls it on
    an interval and appends new rows, which is "live enough" for an
    in-app event feed without adding an ASGI/Channels stack to the
    project.
    """

    TYPE_CHAT = 'chat'
    TYPE_ANNOUNCEMENT = 'announcement'
    MESSAGE_TYPE_CHOICES = (
        (TYPE_CHAT, 'Chat'),
        (TYPE_ANNOUNCEMENT, 'Announcement'),
    )

    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='chat_messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_messages')
    body = models.CharField(max_length=1000)
    message_type = models.CharField(max_length=15, choices=MESSAGE_TYPE_CHOICES, default=TYPE_CHAT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.get_message_type_display()}] {self.sender.username}: {self.body[:40]}"
