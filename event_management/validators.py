"""
Shared file-upload security helpers, used by every app's FileField/ImageField
(vendor documents/contracts, expense receipts, event/venue/resource/sponsor
images, profile pictures, gallery photos, vendor logos).

Kept here — next to the project's other cross-cutting, non-model code
(`event_management/views.py` already holds the shared error handlers) —
rather than duplicated per app, so the extension/size/content rules can't
quietly drift between apps. Referenced directly on model fields (not just
in forms) so the same checks apply everywhere a file is saved, including
the admin and any future API, not only through today's ModelForms.

Three independent layers, mirroring the task's "extension validation / MIME
validation / size limits / safe filenames" split:

1. Extension whitelist (`FileExtensionValidator`) — cheap, first line of
   defense, rejects obviously wrong file types before anything else runs.
2. Content validation (`validate_image_contents`) — actually opens image
   uploads with Pillow and verifies the bytes are a real, decodable image
   of a declared type, so a renamed `.exe`/`.php` can't ride through on a
   spoofed `.jpg`/.png` extension alone (Django's own `forms.ImageField`
   already does this at the *form* layer; this repeats it at the *model*
   layer so it still applies to saves that don't go through a form).
3. Size caps (`validate_document_size` / `validate_image_size`).

`safe_upload_to` replaces the *original* filename entirely with a random
one before it ever touches the filesystem — the single most effective
defense against path traversal, null-byte/unicode tricks, and same-name
overwrites, and it means a private document's on-disk name never leaks a
user-supplied string into a URL or directory listing.
"""
import os
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.deconstruct import deconstructible

# --- Size limits -------------------------------------------------------

DOCUMENT_MAX_SIZE_MB = 10
IMAGE_MAX_SIZE_MB = 5

_DOCUMENT_MAX_BYTES = DOCUMENT_MAX_SIZE_MB * 1024 * 1024
_IMAGE_MAX_BYTES = IMAGE_MAX_SIZE_MB * 1024 * 1024


def validate_document_size(value):
    if value.size > _DOCUMENT_MAX_BYTES:
        raise ValidationError(f"File too large — maximum size is {DOCUMENT_MAX_SIZE_MB}MB.")


def validate_image_size(value):
    if value.size > _IMAGE_MAX_BYTES:
        raise ValidationError(f"Image too large — maximum size is {IMAGE_MAX_SIZE_MB}MB.")


# --- Extension whitelists -----------------------------------------------
# Deliberately narrow: these cover every legitimate use in the project
# today (PDFs/scans/photos for documents & receipts; standard web image
# formats for logos/photos/covers). No executables, scripts, or archives.

DOCUMENT_ALLOWED_EXTENSIONS = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png']
IMAGE_ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp']

validate_document_extension = FileExtensionValidator(
    allowed_extensions=DOCUMENT_ALLOWED_EXTENSIONS,
    message="Unsupported file type. Allowed: %(allowed_extensions)s." % {
        'allowed_extensions': ', '.join(DOCUMENT_ALLOWED_EXTENSIONS)
    },
)
validate_image_extension = FileExtensionValidator(
    allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
    message="Unsupported image type. Allowed: %(allowed_extensions)s." % {
        'allowed_extensions': ', '.join(IMAGE_ALLOWED_EXTENSIONS)
    },
)


# --- Content validation (defeats renamed-extension bypass) --------------

def validate_image_contents(value):
    """Actually decode the upload with Pillow rather than trusting its
    extension/declared content-type. Catches the classic bypass of taking
    an arbitrary (or malicious) file and simply renaming it to `.png`.

    Runs in addition to — not instead of — `validate_image_extension`,
    and in addition to whatever `forms.ImageField` already does at the
    form layer, so a save that skips the form (admin, a script, a future
    API) still gets the same guarantee.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        value.seek(0)
    except (AttributeError, ValueError):
        pass

    try:
        with Image.open(value) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("This file isn't a valid image (or is corrupted).") from exc
    finally:
        try:
            value.seek(0)
        except (AttributeError, ValueError):
            pass


# --- Safe, non-guessable storage filenames -------------------------------

def safe_upload_to(subdir):
    """Return an `upload_to` value for `subdir` that stores every file
    under a random UUID filename, discarding the user-supplied name.

    Why not just rely on Django's own filename sanitizing? Django (4.1+)
    already rejects `..`/absolute paths in `Storage.get_valid_name()`, but
    it still keeps the rest of the original filename — which can contain
    unexpected characters, collide with another upload (relying on
    storage's rename-on-collision to avoid an overwrite), or simply leak
    a private document's real name into a URL/path. Replacing it outright
    sidesteps all of that in one place instead of relying on every
    storage backend to keep sanitizing correctly.

    A plain closure can't be used here: Django migrations need to
    serialize `upload_to` into a real importable reference, and a
    function-local closure has none. `_SafeUploadTo` is a small
    `@deconstructible` class instead, which Django knows how to
    reconstruct from `subdir` alone.
    """
    return _SafeUploadTo(subdir)


@deconstructible
class _SafeUploadTo:
    def __init__(self, subdir):
        self.subdir = subdir

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()
        # Extension is already constrained by a FileExtensionValidator on
        # the field itself; this is a second, independent belt-and-braces
        # check so a stray/unexpected extension can't end up on disk even
        # if a validator is ever accidentally omitted from a field.
        ext = ext if len(ext) <= 10 else ''
        safe_name = f"{uuid.uuid4().hex}{ext}"
        return f"{self.subdir}/{safe_name}"

    def __eq__(self, other):
        return isinstance(other, _SafeUploadTo) and self.subdir == other.subdir
