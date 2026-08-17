from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from events.models import Event
from tickets.models import Ticket
from tickets.utils import render_qr_png
from users.models import User
from .forms import CertificateIssueForm
from .models import Certificate

# Same ownership rule as tickets._can_manage_tickets / budget._can_manage_budget:
# Staff and Super Admin for any event, an Organizer only for their own.


def _can_manage_certs(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


def _can_view_certificate(user, certificate):
    if not user.is_authenticated:
        return False
    if certificate.participant.id == user.id:
        return True
    return _can_manage_certs(user, certificate.event)


@login_required
def certificate_hub(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_manage_certs(request.user, event):
        messages.error(request, "You don't have permission to manage certificates for this event.")
        return redirect('events:event_detail', slug=event.slug)

    attended_tickets = Ticket.objects.filter(
        registration__event=event, status='checked_in'
    ).select_related('registration__user', 'certificate')
    eligible = [t for t in attended_tickets if not hasattr(t, 'certificate')]
    issued = Certificate.objects.filter(ticket__registration__event=event).select_related(
        'ticket__registration__user'
    )

    context = {
        'event': event,
        'eligible_tickets': eligible,
        'issued_certificates': issued,
        'form': CertificateIssueForm(),
    }
    return render(request, 'certificates/certificate_hub.html', context)


@login_required
@require_POST
def certificate_issue(request, ticket_code):
    ticket = get_object_or_404(Ticket, ticket_code=ticket_code)
    event = ticket.event
    if not _can_manage_certs(request.user, event):
        messages.error(request, "You don't have permission to issue certificates for this event.")
        return redirect('events:event_detail', slug=event.slug)

    if ticket.status != 'checked_in':
        messages.error(request, "Certificates can only be issued to attendees who actually checked in.")
        return redirect('certificates:certificate_hub', event_slug=event.slug)

    if hasattr(ticket, 'certificate'):
        messages.info(request, "This attendee already has a certificate.")
        return redirect('certificates:certificate_hub', event_slug=event.slug)

    form = CertificateIssueForm(request.POST)
    if form.is_valid():
        cert = form.save(commit=False)
        cert.ticket = ticket
        cert.issued_by = request.user
        cert.save()
        messages.success(request, f"Certificate issued to {ticket.participant.username}.")
    else:
        messages.error(request, "Couldn't issue certificate — check the form.")
    return redirect('certificates:certificate_hub', event_slug=event.slug)


@login_required
@require_POST
def certificate_bulk_issue(request, event_slug):
    """Issue a default 'Certificate of Attendance' to every checked-in
    ticket for this event that doesn't already have one. The one-by-one
    form above still exists for anyone who wants a badge instead, or a
    custom title for a specific attendee (e.g. a speaker)."""
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_manage_certs(request.user, event):
        messages.error(request, "You don't have permission to issue certificates for this event.")
        return redirect('events:event_detail', slug=event.slug)

    tickets = Ticket.objects.filter(registration__event=event, status='checked_in').select_related('certificate')
    issued_count = 0
    for ticket in tickets:
        if hasattr(ticket, 'certificate'):
            continue
        Certificate.objects.create(ticket=ticket, issued_by=request.user)
        issued_count += 1

    if issued_count:
        messages.success(request, f"Issued {issued_count} certificate(s) for checked-in attendees.")
    else:
        messages.info(request, "No new certificates to issue — everyone who checked in already has one.")
    return redirect('certificates:certificate_hub', event_slug=event.slug)


@login_required
def my_certificates(request):
    certificates = Certificate.objects.filter(ticket__registration__user=request.user).select_related(
        'ticket__registration__event'
    )
    return render(request, 'certificates/my_certificates.html', {'certificates': certificates})


@login_required
def certificate_detail(request, certificate_code):
    certificate = get_object_or_404(Certificate, certificate_code=certificate_code)
    if not _can_view_certificate(request.user, certificate):
        messages.error(request, "You don't have permission to view this certificate.")
        return redirect('dashboard:dashboard')
    return render(request, 'certificates/certificate_detail.html', {'certificate': certificate})


@login_required
def certificate_qr_image(request, certificate_code):
    certificate = get_object_or_404(Certificate, certificate_code=certificate_code)
    if not _can_view_certificate(request.user, certificate):
        return HttpResponse(status=403)
    verify_url = request.build_absolute_uri(certificate.get_verify_url())
    png = render_qr_png(verify_url)
    return HttpResponse(png, content_type='image/png')


@login_required
def certificate_pdf(request, certificate_code):
    certificate = get_object_or_404(
        Certificate.objects.select_related('ticket__registration__event', 'ticket__registration__user'),
        certificate_code=certificate_code
    )
    if not _can_view_certificate(request.user, certificate):
        messages.error(request, "You don't have permission to download this certificate.")
        return redirect('dashboard:dashboard')

    verify_url = request.build_absolute_uri(certificate.get_verify_url())
    pdf_bytes = _build_certificate_pdf(certificate, verify_url)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{certificate.certificate_code}.pdf"'
    return response


def _build_certificate_pdf(certificate, verify_url):
    """Landscape A4 certificate/badge with an embedded QR that resolves to
    the public verification page — same reportlab + qrcode toolchain as
    tickets._build_ticket_pdf, kept as a plain function for the same
    reason (reusable later without duplicating layout)."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    event = certificate.event
    participant = certificate.participant

    buffer = BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    # Border
    c.setStrokeColorRGB(0.55, 0.45, 0.15)
    c.setLineWidth(3)
    c.rect(10 * mm, 10 * mm, width - 20 * mm, height - 20 * mm)

    c.setFillColorRGB(0.09, 0.11, 0.16)
    c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(width / 2, height - 25 * mm, 'Eventra')

    c.setFont('Helvetica-Bold', 28)
    c.drawCentredString(width / 2, height - 45 * mm, certificate.title)

    c.setFont('Helvetica', 12)
    c.drawCentredString(width / 2, height - 60 * mm, 'This is proudly presented to')

    c.setFont('Helvetica-Bold', 22)
    c.drawCentredString(width / 2, height - 72 * mm, participant.get_full_name() or participant.username)

    c.setFont('Helvetica', 12)
    subtitle = 'for successfully attending' if certificate.cert_type == Certificate.TYPE_CERTIFICATE else 'for earning the'
    c.drawCentredString(width / 2, height - 84 * mm, subtitle)

    c.setFont('Helvetica-Bold', 16)
    event_line = event.title if certificate.cert_type == Certificate.TYPE_CERTIFICATE else (
        f"{certificate.get_badge_level_display()} Badge" if certificate.badge_level else certificate.title
    )
    c.drawCentredString(width / 2, height - 94 * mm, event_line[:70])

    c.setFont('Helvetica', 10)
    c.drawCentredString(width / 2, height - 104 * mm, f"Issued {certificate.issued_at.strftime('%B %d, %Y')}")

    # QR + verification code, bottom-right
    qr_png = render_qr_png(verify_url, box_size=4, border=1)
    qr_reader = ImageReader(BytesIO(qr_png))
    qr_size = 28 * mm
    qr_x = width - 25 * mm - qr_size
    qr_y = 15 * mm
    c.drawImage(qr_reader, qr_x, qr_y, width=qr_size, height=qr_size)
    c.setFont('Helvetica', 7)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 5 * mm, 'Scan to verify')
    c.setFont('Helvetica', 8)
    c.drawString(25 * mm, 18 * mm, f"Certificate No. {certificate.certificate_code}")

    c.showPage()
    c.save()
    return buffer.getvalue()


def verify(request, token):
    """Public — no login required. Anyone with the QR (or the printed
    code/link) can confirm a certificate is real, same intent as the
    module plan's 'checks authenticity against a database record'.
    A revoked certificate resolves but is shown as invalid."""
    certificate = Certificate.resolve_token(token)
    context = {'certificate': certificate}
    if certificate and certificate.revoked:
        context['revoked'] = True
    return render(request, 'certificates/verify.html', context)
