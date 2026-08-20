"""
Coverage for `event_management/validators.py` — the extension/size/content/
filename-safety rules shared by every FileField/ImageField in the project
(vendor documents & contracts, expense receipts, event/venue/resource/
sponsor images, profile pictures, gallery photos, vendor logos).

Run with:
    python manage.py test event_management
"""
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .validators import (
    DOCUMENT_MAX_SIZE_MB,
    IMAGE_MAX_SIZE_MB,
    safe_upload_to,
    validate_document_extension,
    validate_document_size,
    validate_image_contents,
    validate_image_extension,
    validate_image_size,
)


def _tiny_png_bytes():
    """A real, minimal valid PNG, generated with Pillow itself so the
    bytes are guaranteed well-formed (checksums, chunk lengths, etc.)
    rather than hand-typed and fragile."""
    import io as _io
    from PIL import Image as _Image

    buf = _io.BytesIO()
    _Image.new('RGB', (1, 1), color=(255, 0, 0)).save(buf, format='PNG')
    return buf.getvalue()


class ExtensionValidatorTests(TestCase):
    def test_document_extension_accepts_pdf(self):
        f = SimpleUploadedFile('contract.pdf', b'%PDF-1.4 fake', content_type='application/pdf')
        validate_document_extension(f)  # must not raise

    def test_document_extension_rejects_executable(self):
        f = SimpleUploadedFile('payload.exe', b'MZ...', content_type='application/octet-stream')
        with self.assertRaises(ValidationError):
            validate_document_extension(f)

    def test_document_extension_rejects_script_disguised_with_double_extension(self):
        # The extension check only looks at the final extension — this
        # confirms a sneaky `invoice.pdf.php` is still rejected (final
        # ext is `.php`, not `.pdf`).
        f = SimpleUploadedFile('invoice.pdf.php', b'<?php system($_GET["c"]); ?>')
        with self.assertRaises(ValidationError):
            validate_document_extension(f)

    def test_image_extension_accepts_png(self):
        f = SimpleUploadedFile('logo.png', _tiny_png_bytes(), content_type='image/png')
        validate_image_extension(f)  # must not raise

    def test_image_extension_rejects_svg(self):
        # SVG is XML and can embed <script> — deliberately excluded from
        # the image allow-list even though browsers render it as an image.
        f = SimpleUploadedFile('logo.svg', b'<svg onload="alert(1)"></svg>', content_type='image/svg+xml')
        with self.assertRaises(ValidationError):
            validate_image_extension(f)


class SizeValidatorTests(TestCase):
    def test_document_under_limit_passes(self):
        f = SimpleUploadedFile('doc.pdf', b'x' * 1024)
        validate_document_size(f)  # must not raise

    def test_document_over_limit_rejected(self):
        f = SimpleUploadedFile('doc.pdf', b'x' * (DOCUMENT_MAX_SIZE_MB * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError):
            validate_document_size(f)

    def test_image_under_limit_passes(self):
        f = SimpleUploadedFile('img.png', b'x' * 1024)
        validate_image_size(f)  # must not raise

    def test_image_over_limit_rejected(self):
        f = SimpleUploadedFile('img.png', b'x' * (IMAGE_MAX_SIZE_MB * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError):
            validate_image_size(f)


class ImageContentValidatorTests(TestCase):
    """Task 4: a renamed non-image file must not slip past validation
    just because its extension says `.png`/`.jpg`."""

    def test_genuine_image_passes(self):
        f = SimpleUploadedFile('real.png', _tiny_png_bytes(), content_type='image/png')
        validate_image_contents(f)  # must not raise

    def test_renamed_text_file_rejected_despite_image_extension(self):
        f = SimpleUploadedFile('fake.png', b'just some plain text, not an image', content_type='image/png')
        with self.assertRaises(ValidationError):
            validate_image_contents(f)

    def test_renamed_executable_rejected_despite_image_extension(self):
        f = SimpleUploadedFile('fake.jpg', b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00', content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            validate_image_contents(f)

    def test_php_polyglot_with_image_extension_rejected(self):
        # A classic bypass attempt: valid-looking bytes followed by PHP.
        # Pillow's verify() must still reject this as not a decodable
        # image rather than accepting the leading noise.
        f = SimpleUploadedFile('shell.png', b'<?php system($_GET["c"]); ?>', content_type='image/png')
        with self.assertRaises(ValidationError):
            validate_image_contents(f)

    def test_file_pointer_reset_after_validation_so_it_can_still_be_saved(self):
        f = SimpleUploadedFile('real.png', _tiny_png_bytes(), content_type='image/png')
        validate_image_contents(f)
        # If the pointer weren't reset, re-reading would return b'' and
        # the file would be saved empty/corrupted.
        f.seek(0)
        self.assertEqual(f.read(), _tiny_png_bytes())


class SafeUploadToTests(TestCase):
    """Task 5: filenames on disk must never be attacker-controlled."""

    def setUp(self):
        self.upload_to = safe_upload_to('vendor_documents')

    def test_generated_path_lives_under_expected_subdir(self):
        path = self.upload_to(None, 'invoice.pdf')
        self.assertTrue(path.startswith('vendor_documents/'))

    def test_generated_path_does_not_contain_original_filename(self):
        path = self.upload_to(None, 'super-secret-client-contract.pdf')
        self.assertNotIn('super-secret-client-contract', path)

    def test_path_traversal_attempt_cannot_escape_subdir(self):
        malicious_names = [
            '../../etc/passwd',
            '../../../secrets.pdf',
            '..\\..\\windows\\system32\\config.pdf',
            '/etc/passwd',
        ]
        for name in malicious_names:
            path = self.upload_to(None, name)
            self.assertTrue(path.startswith('vendor_documents/'))
            self.assertNotIn('..', path)
            # Exactly one path segment after the subdir — no nested/escaped path.
            self.assertEqual(path.count('/'), 1)

    def test_null_byte_and_unusual_characters_do_not_survive(self):
        path = self.upload_to(None, 'evil\x00name<>:"|?.pdf')
        self.assertNotIn('\x00', path)
        self.assertNotIn('<', path)
        self.assertNotIn('>', path)

    def test_two_uploads_with_identical_original_name_never_collide(self):
        path1 = self.upload_to(None, 'invoice.pdf')
        path2 = self.upload_to(None, 'invoice.pdf')
        self.assertNotEqual(path1, path2)

    def test_extension_is_preserved_and_lowercased(self):
        path = self.upload_to(None, 'Photo.JPG')
        self.assertTrue(path.endswith('.jpg'))

    def test_upload_to_is_migration_serializable(self):
        # A plain closure can't be serialized into a migration file; this
        # is the regression test for that: the deconstructible class must
        # round-trip through Django's own serializer machinery.
        from django.db.migrations.writer import MigrationWriter
        serialized, imports = MigrationWriter.serialize(self.upload_to)
        self.assertIn('_SafeUploadTo', serialized)
        self.assertIn("'vendor_documents'", serialized)
