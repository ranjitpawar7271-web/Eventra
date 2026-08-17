import sys

from django.apps import apps
from django.conf import settings
from django import get_version as django_version
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

# A curated set of core models to show row counts for — not every model
# in the project, just enough to sanity-check "is this install actually
# holding data" at a glance. Missing/renamed models are skipped rather
# than erroring, so this page keeps working across future migrations.
HEALTH_MODEL_LIST = [
    ('users', 'User'),
    ('events', 'Event'),
    ('events', 'Registration'),
    ('tickets', 'Ticket'),
    ('certificates', 'Certificate'),
    ('tasks', 'Task'),
    ('budget', 'EventBudget'),
    ('support', 'SupportRequest'),
]


def check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return True, ''
    except Exception as exc:
        return False, str(exc)


def count_pending_migrations():
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return len(plan)
    except Exception:
        return None


def get_model_counts():
    counts = []
    for app_label, model_name in HEALTH_MODEL_LIST:
        try:
            model = apps.get_model(app_label, model_name)
            counts.append({'label': f'{app_label}.{model_name}', 'count': model.objects.count()})
        except LookupError:
            continue
    return counts


def get_system_health():
    db_ok, db_error = check_database()
    return {
        'db_ok': db_ok,
        'db_error': db_error,
        'pending_migrations': count_pending_migrations(),
        'model_counts': get_model_counts(),
        'django_version': django_version(),
        'python_version': sys.version.split()[0],
        'debug_mode': settings.DEBUG,
    }
