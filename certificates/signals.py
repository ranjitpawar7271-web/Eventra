"""Notify a participant when their certificate is issued.

A signal rather than editing certificate_issue/certificate_bulk_issue
directly, so both paths (and any future one) get this for free — same
additive pattern used across the project for cross-app notifications
(see tickets/signals.py, workflow/signals.py).
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Certificate


@receiver(post_save, sender=Certificate)
def notify_certificate_issued(sender, instance, created, **kwargs):
    if not created:
        return

    from workflow.models import Notification

    certificate = instance
    Notification.notify(
        certificate.participant,
        f"Your certificate for \"{certificate.event.title}\" is ready to download.",
        link=certificate.get_absolute_url(),
        notification_type=Notification.TYPE_CERTIFICATE,
        related_event=certificate.event,
        dedupe_key=f'certificate-ready-{certificate.pk}',
    )
