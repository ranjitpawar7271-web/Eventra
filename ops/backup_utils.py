import io
import json
import os
import tempfile

from django.core import serializers
from django.core.management import call_command
from django.db import transaction

# Excluded from backups for the same reason Django's own docs recommend
# it: these tables are either regenerated automatically (contenttypes,
# permissions) or are inherently environment-specific / not meaningful
# to restore (sessions, admin's own action log). Restoring them from a
# backup taken on a different run risks primary-key collisions with
# freshly-created rows that have nothing to do with the actual data.
BACKUP_EXCLUDED_APPS = ['contenttypes', 'sessions', 'admin.logentry', 'auth.permission']


def create_backup_json():
    """Returns (json_text, object_count) for a full-data JSON backup,
    using Django's own `dumpdata` — no custom serialization format to
    maintain or get subtly wrong."""
    buffer = io.StringIO()
    call_command(
        'dumpdata',
        exclude=BACKUP_EXCLUDED_APPS,
        indent=2,
        stdout=buffer,
    )
    content = buffer.getvalue()
    try:
        object_count = len(json.loads(content))
    except (ValueError, TypeError):
        object_count = 0
    return content, object_count


class RestoreValidationError(Exception):
    pass


def validate_restore_content(content):
    """Parses (but does not save) the uploaded content as a Django
    fixture, raising RestoreValidationError with a human-readable reason
    if it isn't one. Returns the object count. This is the check that
    happens *before* anything touches the database — an invalid or
    corrupt upload should fail loudly here, not partway through
    `loaddata`."""
    try:
        deserialized = list(serializers.deserialize('json', content))
    except (serializers.base.DeserializationError, ValueError, json.JSONDecodeError) as exc:
        raise RestoreValidationError(f"Not a valid backup file: {exc}") from exc

    if not deserialized:
        raise RestoreValidationError("This file doesn't contain any records to restore.")

    return len(deserialized)


def execute_restore(content):
    """Loads a previously-validated backup file into the database inside
    a transaction — if anything fails partway through, nothing is left
    half-applied. Returns the number of objects loaded.

    Caller is expected to have already called validate_restore_content()
    first; this function re-validates anyway (cheap, and never trust a
    second code path silently skipped that check)."""
    object_count = validate_restore_content(content)

    fd, tmp_path = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        with transaction.atomic():
            call_command('loaddata', tmp_path, verbosity=0)
    finally:
        os.unlink(tmp_path)

    return object_count
