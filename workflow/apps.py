from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workflow'
    verbose_name = 'Workflow, Notifications & Calendar'

    def ready(self):
        # Connects the Event publish gate and the cross-module "something
        # happened, tell someone" signals (staff assignment, vendor
        # contract sent). Imported here, not at module load time, for the
        # same ordering reason Module 7's tickets app does it.
        from . import signals  # noqa: F401
