from django.conf import settings
from django.db import models


class PlatformSettings(models.Model):
    """Site-wide configuration (Module 10's 'Admin Settings Panel').
    Singleton: always exactly one row, enforced via `load()`/`save()`
    rather than a database constraint — Django doesn't have a clean
    built-in for "exactly one row," and a save()-level guard is simpler
    and sufficient for something only ever edited through this app's own
    form.
    """

    site_name = models.CharField(max_length=100, default='Eventra')
    support_email = models.EmailField(default='support@example.com')
    allow_new_signups = models.BooleanField(
        default=True, help_text="If off, the signup page still loads but rejects new account creation."
    )
    maintenance_mode = models.BooleanField(
        default=False,
        help_text="If on, everyone except Super Admins sees a maintenance page for the whole site."
    )
    maintenance_message = models.TextField(
        blank=True, default="We're performing scheduled maintenance. Please check back shortly."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='platform_settings_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'platform settings'

    def __str__(self):
        return 'Platform Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # The singleton is never meant to be deleted through normal use —
        # there's no "no settings" state, only default settings.
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
