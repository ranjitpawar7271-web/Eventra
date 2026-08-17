from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Organization(models.Model):
    """The multi-tenant foundation (Module 10's 'Organization Management' /
    'Multi-tenant Architecture' items). Architecture decision, made
    explicit here rather than left implicit: **shared-schema with an FK**,
    not separate-schema-per-tenant. Separate schemas mean per-tenant
    migrations and connection routing — real, ongoing operational cost
    this project has no need for at this scale. A shared schema with a
    foreign key is the standard choice and works with Django's ORM
    unmodified.

    Scope of what this actually touches: this model exists, and
    `events.Event.organization` (nullable, added in this same delivery)
    lets an event optionally belong to one. Almost every other model in
    the project already chains back to Event via FK — budget, tasks,
    certificates, sponsorships, surveys, chat, gallery — so scoping at
    the Event level gets transitive org-scoping for nearly the whole
    system without touching any of those apps' own models.

    What this deliberately does NOT do: none of those apps' *views* have
    been changed to filter by organization. The data model to support
    multi-tenancy exists; enforcing per-org data isolation everywhere
    data is queried is a separate, much larger effort across dozens of
    views, and attempting that in one uncontrolled pass would risk
    silently breaking access control across a system with 296 passing
    tests built on a single-tenant assumption. That's follow-on work,
    not something to fake as "done" here.
    """

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='organizations_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('organizations:organization_detail', kwargs={'slug': self.slug})

    @property
    def member_count(self):
        return self.memberships.count()

    @property
    def event_count(self):
        return self.events.count()


class OrganizationMembership(models.Model):
    """A user's role within one organization. A many-to-many-with-role
    relation rather than a single FK on User — deliberately, since a
    person can reasonably belong to more than one organization (a vendor
    or sponsor contact working across multiple client orgs, for
    instance), and this way nothing on the core `User` model needed to
    change at all.
    """

    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = (
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MEMBER, 'Member'),
    )

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='organization_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['organization', 'role']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'user'], name='unique_org_membership')
        ]

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()} of {self.organization.name}"
