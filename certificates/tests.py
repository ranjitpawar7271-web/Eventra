from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Registration
from tickets.models import Ticket
from users.models import User
from .models import Certificate


def make_event(organizer, title='Test Event'):
    now = timezone.now()
    return Event.objects.create(
        title=title,
        description='A test event.',
        organizer=organizer,
        location='Community Hall',
        start_date=now + timedelta(days=1),
        end_date=now + timedelta(days=1, hours=3),
        capacity=100,
        price=0,
    )


def confirm_and_get_ticket(event, user):
    registration = Registration.objects.create(event=event, user=user, status='confirmed')
    return Ticket.objects.get(registration=registration)


class CertificateModelTests(TestCase):
    def test_code_and_token_auto_generated(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        event = make_event(organizer)
        ticket = confirm_and_get_ticket(event, participant)
        ticket.status = 'checked_in'
        ticket.save()

        cert = Certificate.objects.create(ticket=ticket)
        self.assertTrue(cert.certificate_code.startswith('CERT-'))
        self.assertTrue(cert.verify_token)

    def test_resolve_token_round_trip(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        event = make_event(organizer)
        ticket = confirm_and_get_ticket(event, participant)
        ticket.status = 'checked_in'
        ticket.save()
        cert = Certificate.objects.create(ticket=ticket)

        resolved = Certificate.resolve_token(cert.verify_token)
        self.assertEqual(resolved.pk, cert.pk)

    def test_resolve_token_rejects_tampered_token(self):
        self.assertIsNone(Certificate.resolve_token('not-a-real-token'))


class CertificateIssuePermissionTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.other_organizer = User.objects.create_user(username='org2', password='pw12345!', role=User.ORGANIZER)
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)
        self.ticket = confirm_and_get_ticket(self.event, self.participant)

    def test_cannot_issue_certificate_without_checkin(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.post(
            reverse('certificates:certificate_issue', kwargs={'ticket_code': self.ticket.ticket_code}),
            {'cert_type': 'certificate', 'title': 'Certificate of Attendance', 'badge_level': ''}
        )
        self.assertFalse(Certificate.objects.filter(ticket=self.ticket).exists())

    def test_organizer_can_issue_for_own_checked_in_ticket(self):
        self.ticket.status = 'checked_in'
        self.ticket.save()
        self.client.login(username='org1', password='pw12345!')
        self.client.post(
            reverse('certificates:certificate_issue', kwargs={'ticket_code': self.ticket.ticket_code}),
            {'cert_type': 'certificate', 'title': 'Certificate of Attendance', 'badge_level': ''}
        )
        self.assertTrue(Certificate.objects.filter(ticket=self.ticket).exists())

    def test_other_organizer_cannot_issue(self):
        self.ticket.status = 'checked_in'
        self.ticket.save()
        self.client.login(username='org2', password='pw12345!')
        self.client.post(
            reverse('certificates:certificate_issue', kwargs={'ticket_code': self.ticket.ticket_code}),
            {'cert_type': 'certificate', 'title': 'Certificate of Attendance', 'badge_level': ''}
        )
        self.assertFalse(Certificate.objects.filter(ticket=self.ticket).exists())

    def test_bulk_issue_only_covers_checked_in_without_existing_cert(self):
        participant2 = User.objects.create_user(username='part2', password='pw12345!', role=User.PARTICIPANT)
        ticket2 = confirm_and_get_ticket(self.event, participant2)
        # ticket (self.ticket): checked in, no cert yet -> should get one
        self.ticket.status = 'checked_in'
        self.ticket.save()
        # ticket2: never checked in -> should NOT get one
        self.client.login(username='org1', password='pw12345!')
        self.client.post(reverse('certificates:certificate_bulk_issue', kwargs={'event_slug': self.event.slug}))

        self.assertTrue(Certificate.objects.filter(ticket=self.ticket).exists())
        self.assertFalse(Certificate.objects.filter(ticket=ticket2).exists())

    def test_bulk_issue_does_not_duplicate_existing_certificates(self):
        self.ticket.status = 'checked_in'
        self.ticket.save()
        Certificate.objects.create(ticket=self.ticket, issued_by=self.staff)

        self.client.login(username='staff1', password='pw12345!')
        self.client.post(reverse('certificates:certificate_bulk_issue', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(Certificate.objects.filter(ticket=self.ticket).count(), 1)


class CertificateAccessTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        self.participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        self.stranger = User.objects.create_user(username='stranger1', password='pw12345!', role=User.PARTICIPANT)
        self.event = make_event(self.organizer)
        self.ticket = confirm_and_get_ticket(self.event, self.participant)
        self.ticket.status = 'checked_in'
        self.ticket.save()
        self.cert = Certificate.objects.create(ticket=self.ticket)

    def test_owner_can_view_own_certificate(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(self.cert.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_stranger_cannot_view_certificate(self):
        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.get(self.cert.get_absolute_url())
        self.assertRedirects(response, reverse('dashboard:dashboard'))

    def test_public_verify_valid_certificate_no_login_required(self):
        response = self.client.get(reverse('certificates:verify', kwargs={'token': self.cert.verify_token}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['certificate'].pk, self.cert.pk)

    def test_public_verify_invalid_token(self):
        response = self.client.get(reverse('certificates:verify', kwargs={'token': 'garbage-token'}))
        self.assertIsNone(response.context['certificate'])

    def test_public_verify_revoked_certificate_shown_invalid(self):
        self.cert.revoked = True
        self.cert.save()
        response = self.client.get(reverse('certificates:verify', kwargs={'token': self.cert.verify_token}))
        self.assertTrue(response.context.get('revoked'))

    def test_my_certificates_only_shows_own(self):
        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('certificates:my_certificates'))
        self.assertIn(self.cert, list(response.context['certificates']))

        self.client.login(username='stranger1', password='pw12345!')
        response = self.client.get(reverse('certificates:my_certificates'))
        self.assertNotIn(self.cert, list(response.context['certificates']))


class CertificatePDFTests(TestCase):
    """Smoke test: the reportlab/qrcode build path itself doesn't error."""

    def test_pdf_download_returns_pdf_bytes(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        event = make_event(organizer)
        ticket = confirm_and_get_ticket(event, participant)
        ticket.status = 'checked_in'
        ticket.save()
        cert = Certificate.objects.create(ticket=ticket, cert_type='badge', badge_level='gold', title='Volunteer Badge')

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('certificates:certificate_pdf', kwargs={'certificate_code': cert.certificate_code}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_qr_image_returns_png(self):
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        participant = User.objects.create_user(username='part1', password='pw12345!', role=User.PARTICIPANT)
        event = make_event(organizer)
        ticket = confirm_and_get_ticket(event, participant)
        ticket.status = 'checked_in'
        ticket.save()
        cert = Certificate.objects.create(ticket=ticket)

        self.client.login(username='part1', password='pw12345!')
        response = self.client.get(reverse('certificates:certificate_qr', kwargs={'certificate_code': cert.certificate_code}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
