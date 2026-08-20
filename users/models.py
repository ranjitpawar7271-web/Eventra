from django.contrib.auth.models import AbstractUser
from django.db import models

from event_management.validators import (
    safe_upload_to, validate_image_contents, validate_image_extension, validate_image_size,
)


class User(AbstractUser):
    """Custom user model extending Django's AbstractUser with profile
    fields and a platform-wide role used for permission checks.
    """

    # --- Role-based access control -----------------------------------
    # Roles are additive on top of Django's built-in is_staff/is_superuser
    # flags, they do not replace them. `role` drives feature-level
    # permissions across the app (which dashboard a user sees, which
    # actions they may perform, etc.).
    SUPER_ADMIN = 'super_admin'
    ORGANIZER = 'organizer'
    STAFF = 'staff'
    VENDOR = 'vendor'
    VOLUNTEER = 'volunteer'
    PARTICIPANT = 'participant'

    ROLE_CHOICES = (
        (SUPER_ADMIN, 'Super Admin'),
        (ORGANIZER, 'Organizer'),
        (STAFF, 'Staff'),
        (VENDOR, 'Vendor'),
        (VOLUNTEER, 'Volunteer'),
        (PARTICIPANT, 'Participant'),
    )

    # Roles a person can pick for themselves at sign-up. Super Admin and
    # Staff are privileged/operational roles and must be granted by an
    # existing admin (via Django admin or a future "Manage Users" module),
    # never self-selected.
    SELF_SERVICE_ROLES = (ORGANIZER, VENDOR, VOLUNTEER, PARTICIPANT)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=PARTICIPANT,
        help_text="Determines which dashboard and permissions the user gets.",
    )

    phone_number = models.CharField(max_length=15, blank=True)
    bio = models.TextField(max_length=300, blank=True)
    profile_image = models.ImageField(
        upload_to=safe_upload_to('profile_images'), blank=True, null=True,
        validators=[validate_image_extension, validate_image_size, validate_image_contents],
    )
    is_organizer = models.BooleanField(
        default=False,
        help_text="Organizers can create and manage events. Kept for backward "
                   "compatibility; automatically kept in sync with `role`."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        # Keep the legacy `is_organizer` flag in sync with the new role
        # system so existing code/templates that check it keep working.
        update_fields = kwargs.get('update_fields')

        if self.role == self.ORGANIZER:
            self.is_organizer = True
            if update_fields is not None and 'is_organizer' not in update_fields and 'role' in update_fields:
                kwargs['update_fields'] = list(update_fields) + ['is_organizer']
        elif self.is_organizer and self.role == self.PARTICIPANT:
            # Legacy code path (events/views.py) flips is_organizer=True
            # the first time a participant creates an event. Promote
            # their role to match, instead of leaving the two out of sync.
            self.role = self.ORGANIZER
            if update_fields is not None and 'role' not in update_fields:
                # Caller used save(update_fields=[...]) without knowing
                # about `role` — make sure our derived change actually
                # gets written, not silently dropped.
                kwargs['update_fields'] = list(update_fields) + ['role']

        super().save(*args, **kwargs)

    @property
    def initials(self):
        first = self.first_name[:1] if self.first_name else self.username[:1]
        last = self.last_name[:1] if self.last_name else ''
        return f"{first}{last}".upper()

    # --- Role helpers ---------------------------------------------------
    @property
    def is_super_admin(self):
        return self.role == self.SUPER_ADMIN or self.is_superuser

    @property
    def is_staff_role(self):
        return self.role == self.STAFF

    @property
    def is_vendor(self):
        return self.role == self.VENDOR

    @property
    def is_volunteer(self):
        return self.role == self.VOLUNTEER

    @property
    def is_participant(self):
        return self.role == self.PARTICIPANT

    @property
    def can_manage_events(self):
        """Roles allowed to create/edit/publish events."""
        return self.role in (self.SUPER_ADMIN, self.ORGANIZER, self.STAFF) or self.is_superuser
