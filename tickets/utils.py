"""QR image rendering helpers.

Signing/verifying the payload lives on Ticket itself (models.py, using
Django's built-in `signing` module — no new dependency needed for that
part). This module only turns an already-signed token into a scannable
PNG, which does need the `qrcode` package (see requirements.txt).
"""
from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def render_qr_png(data, box_size=8, border=2):
    """Render `data` (the signed QR token string) to PNG bytes."""
    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')

    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
