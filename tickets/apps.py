from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tickets'

    def ready(self):
        # Registers the Registration post_save signal that auto-issues/
        # cancels tickets. Importing here (not at module load time) keeps
        # the app-loading order safe, same reason Django itself recommends
        # connecting signals inside ready().
        from . import signals  # noqa: F401
