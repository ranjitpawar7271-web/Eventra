from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import Currency
from .utils import get_active_currency


class CurrencyModelTests(TestCase):
    def test_convert_from_base(self):
        usd = Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012000'))
        self.assertEqual(usd.convert_from_base(Decimal('1000')), Decimal('12.00'))

    def test_convert_from_base_handles_bad_input_gracefully(self):
        usd = Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012'))
        self.assertEqual(usd.convert_from_base(None), Decimal('0.00'))

    def test_get_base_returns_marked_currency(self):
        Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012'))
        inr = Currency.objects.create(code='INR', name='Indian Rupee', symbol='₹', rate_to_base=1, is_base=True)
        self.assertEqual(Currency.get_base(), inr)


class ActiveCurrencyResolutionTests(TestCase):
    """Covers currency.utils.get_active_currency — the fallback chain
    (session choice -> base currency -> synthetic identity currency)
    matters because it must never break price display, even on a fresh
    install with zero Currency rows."""

    def test_falls_back_to_synthetic_identity_currency_when_none_configured(self):
        request = self.client.get('/').wsgi_request
        currency = get_active_currency(request)
        self.assertEqual(currency.code, 'INR')
        self.assertEqual(currency.convert_from_base(Decimal('500')), Decimal('500.00'))

    def test_falls_back_to_base_currency_when_no_session_choice(self):
        Currency.objects.create(code='INR', name='Indian Rupee', symbol='₹', rate_to_base=1, is_base=True)
        Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012'))
        request = self.client.get('/').wsgi_request
        currency = get_active_currency(request)
        self.assertEqual(currency.code, 'INR')

    def test_uses_session_choice_when_set(self):
        Currency.objects.create(code='INR', name='Indian Rupee', symbol='₹', rate_to_base=1, is_base=True)
        Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012'))
        session = self.client.session
        session['display_currency_code'] = 'USD'
        session.save()
        request = self.client.get('/').wsgi_request
        currency = get_active_currency(request)
        self.assertEqual(currency.code, 'USD')


class DisplayPriceTagTests(TestCase):
    """Confirms the actual end-to-end behavior: the event list page
    renders a converted price once a display currency is selected, not
    just that the tag function works in isolation."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from events.models import Event
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        now = timezone.now()
        self.event = Event.objects.create(
            title='Paid Event', description='x', organizer=self.organizer, location='Hall',
            start_date=now + timedelta(days=5), end_date=now + timedelta(days=5, hours=2),
            capacity=50, price=Decimal('1000'), status='published',
        )
        Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012000'))

    def test_price_shown_in_selected_currency_on_event_list(self):
        session = self.client.session
        session['display_currency_code'] = 'USD'
        session.save()
        response = self.client.get(reverse('events:event_list'))
        self.assertContains(response, '$12.00')


class CurrencyManagementPermissionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff1', password='pw12345!', role=User.STAFF)
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)

    def test_only_staff_admin_can_manage_currencies(self):
        self.client.login(username='org1', password='pw12345!')
        response = self.client.get(reverse('currency:currency_list'))
        self.assertRedirects(response, reverse('dashboard:dashboard'))

        self.client.login(username='staff1', password='pw12345!')
        response = self.client.get(reverse('currency:currency_list'))
        self.assertEqual(response.status_code, 200)

    def test_setting_new_base_currency_unsets_previous_base(self):
        self.client.login(username='staff1', password='pw12345!')
        inr = Currency.objects.create(code='INR', name='Indian Rupee', symbol='₹', rate_to_base=1, is_base=True)
        self.client.post(reverse('currency:currency_create'), {
            'code': 'USD', 'name': 'US Dollar', 'symbol': '$', 'rate_to_base': '0.012', 'is_base': True,
        })
        inr.refresh_from_db()
        self.assertFalse(inr.is_base)
        self.assertTrue(Currency.objects.get(code='USD').is_base)

    def test_set_display_currency_is_public(self):
        Currency.objects.create(code='USD', name='US Dollar', symbol='$', rate_to_base=Decimal('0.012'))
        response = self.client.post(reverse('currency:set_display_currency'), {'currency': 'USD', 'next': '/'})
        self.assertEqual(self.client.session.get('display_currency_code'), 'USD')

    def test_set_display_currency_rejects_unknown_code(self):
        response = self.client.post(reverse('currency:set_display_currency'), {'currency': 'ZZZ', 'next': '/'})
        self.assertNotIn('display_currency_code', self.client.session)


class HindiTranslationTests(TestCase):
    """Confirms the compiled Hindi translation (locale/hi/LC_MESSAGES/
    django.mo) actually renders — not just that {% trans %} tags exist
    in templates, but that a real .po/.mo pair was generated with
    gettext and Django picks it up correctly when the 'hi' locale is
    active. See the Module 10 delivery notes for the scope of what's
    translated (navbar only, as a representative subset — not every
    string across the whole project)."""

    def test_navbar_renders_in_english_by_default(self):
        response = self.client.get(reverse('pages:home'))
        self.assertContains(response, 'Home')
        self.assertContains(response, 'Sign Up')

    def test_navbar_renders_in_hindi_when_locale_active(self):
        from django.utils import translation
        with translation.override('hi'):
            response = self.client.get(reverse('pages:home'), HTTP_ACCEPT_LANGUAGE='hi')
        self.assertContains(response, 'होम')
        self.assertContains(response, 'साइन अप')

    def test_language_switch_view_persists_choice_in_cookie(self):
        from django.conf import settings
        response = self.client.post(reverse('set_language'), {'language': 'hi', 'next': '/'})
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'hi')

        followup = self.client.get('/', HTTP_COOKIE=f'{settings.LANGUAGE_COOKIE_NAME}=hi')
        self.assertContains(followup, 'होम')
