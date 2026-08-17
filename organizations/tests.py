from django.test import TestCase
from django.urls import reverse

from users.models import User
from .models import Organization, OrganizationMembership


class OrganizationModelTests(TestCase):
    def test_slug_auto_generated_and_unique(self):
        o1 = Organization.objects.create(name='Acme Corp')
        o2 = Organization.objects.create(name='Acme Corp Events')
        self.assertEqual(o1.slug, 'acme-corp')
        self.assertNotEqual(o1.slug, o2.slug)

    def test_member_and_event_counts(self):
        org = Organization.objects.create(name='Acme Corp')
        user = User.objects.create_user(username='u1', password='pw12345!', role=User.PARTICIPANT)
        self.assertEqual(org.member_count, 0)
        OrganizationMembership.objects.create(organization=org, user=user, role='member')
        self.assertEqual(org.member_count, 1)


class OrganizationCreationPermissionTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        self.organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)

    def test_only_super_admin_can_create_organization(self):
        self.client.login(username='org1', password='pw12345!')
        self.client.post(reverse('organizations:organization_create'), {
            'name': 'Blocked Org', 'description': '', 'is_active': True
        })
        self.assertFalse(Organization.objects.filter(name='Blocked Org').exists())

        self.client.login(username='admin1', password='pw12345!')
        self.client.post(reverse('organizations:organization_create'), {
            'name': 'Allowed Org', 'description': '', 'is_active': True
        })
        org = Organization.objects.get(name='Allowed Org')
        # Creator is automatically made Owner.
        membership = OrganizationMembership.objects.get(organization=org, user=self.super_admin)
        self.assertEqual(membership.role, 'owner')


class OrganizationMembershipPermissionTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        self.owner = User.objects.create_user(username='owner1', password='pw12345!', role=User.ORGANIZER)
        self.admin_member = User.objects.create_user(username='adm1', password='pw12345!', role=User.ORGANIZER)
        self.regular_member = User.objects.create_user(username='mem1', password='pw12345!', role=User.PARTICIPANT)
        self.outsider = User.objects.create_user(username='out1', password='pw12345!', role=User.PARTICIPANT)

        self.org = Organization.objects.create(name='Acme Corp', created_by=self.owner)
        OrganizationMembership.objects.create(organization=self.org, user=self.owner, role='owner')
        OrganizationMembership.objects.create(organization=self.org, user=self.admin_member, role='admin')

    def test_outsider_cannot_view_organization_detail(self):
        self.client.login(username='out1', password='pw12345!')
        response = self.client.get(self.org.get_absolute_url())
        self.assertRedirects(response, reverse('organizations:organization_list'))

    def test_member_can_view_but_not_manage(self):
        OrganizationMembership.objects.create(organization=self.org, user=self.regular_member, role='member')
        self.client.login(username='mem1', password='pw12345!')
        response = self.client.get(self.org.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_manage'])

    def test_admin_can_add_member_but_not_grant_owner(self):
        self.client.login(username='adm1', password='pw12345!')
        response = self.client.post(reverse('organizations:membership_add', kwargs={'slug': self.org.slug}), {
            'username': 'out1', 'role': 'owner',
        })
        self.assertFalse(OrganizationMembership.objects.filter(organization=self.org, user=self.outsider).exists())

        response = self.client.post(reverse('organizations:membership_add', kwargs={'slug': self.org.slug}), {
            'username': 'out1', 'role': 'member',
        })
        self.assertTrue(OrganizationMembership.objects.filter(organization=self.org, user=self.outsider, role='member').exists())

    def test_owner_can_grant_owner(self):
        self.client.login(username='owner1', password='pw12345!')
        self.client.post(reverse('organizations:membership_add', kwargs={'slug': self.org.slug}), {
            'username': 'out1', 'role': 'owner',
        })
        self.assertTrue(OrganizationMembership.objects.filter(organization=self.org, user=self.outsider, role='owner').exists())

    def test_admin_cannot_remove_owner(self):
        owner_membership = OrganizationMembership.objects.get(organization=self.org, user=self.owner)
        self.client.login(username='adm1', password='pw12345!')
        self.client.post(reverse('organizations:membership_remove', kwargs={'pk': owner_membership.pk}))
        self.assertTrue(OrganizationMembership.objects.filter(pk=owner_membership.pk).exists())

    def test_only_super_admin_can_delete_organization(self):
        self.client.login(username='owner1', password='pw12345!')
        response = self.client.post(reverse('organizations:organization_delete', kwargs={'slug': self.org.slug}))
        self.assertTrue(Organization.objects.filter(pk=self.org.pk).exists())

        self.client.login(username='admin1', password='pw12345!')
        self.client.post(reverse('organizations:organization_delete', kwargs={'slug': self.org.slug}))
        self.assertFalse(Organization.objects.filter(pk=self.org.pk).exists())


class EventOrganizationFieldBackwardCompatTests(TestCase):
    """The whole point of making this field nullable and additive: an
    Event created exactly the way every pre-existing test in this
    project creates one (no `organization` kwarg at all) must keep
    working identically, with organization simply defaulting to None."""

    def test_event_created_without_organization_kwarg_still_works(self):
        from datetime import timedelta
        from django.utils import timezone
        from events.models import Event

        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        now = timezone.now()
        event = Event.objects.create(
            title='No-org Event', description='x', organizer=organizer, location='Hall',
            start_date=now + timedelta(days=5), end_date=now + timedelta(days=5, hours=2),
            capacity=50, price=0,
        )
        self.assertIsNone(event.organization)

    def test_event_form_scopes_organization_choices_to_users_own_orgs(self):
        from events.forms import EventForm
        organizer = User.objects.create_user(username='org1', password='pw12345!', role=User.ORGANIZER)
        my_org = Organization.objects.create(name='My Org')
        other_org = Organization.objects.create(name='Other Org')
        OrganizationMembership.objects.create(organization=my_org, user=organizer, role='member')

        form = EventForm(user=organizer)
        org_choices = list(form.fields['organization'].queryset)
        self.assertIn(my_org, org_choices)
        self.assertNotIn(other_org, org_choices)

    def test_super_admin_sees_all_organizations_in_event_form(self):
        from events.forms import EventForm
        super_admin = User.objects.create_user(username='admin1', password='pw12345!', role=User.SUPER_ADMIN)
        org_a = Organization.objects.create(name='Org A')
        org_b = Organization.objects.create(name='Org B')

        form = EventForm(user=super_admin)
        org_choices = list(form.fields['organization'].queryset)
        self.assertIn(org_a, org_choices)
        self.assertIn(org_b, org_choices)
