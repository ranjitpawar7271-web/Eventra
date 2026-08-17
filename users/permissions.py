"""
Role-based access control helpers.

These are intentionally generic so every future module (venues, resources,
vendors, staff, budgets, tickets, ...) can reuse the same permission layer
instead of re-implementing role checks per-view.

Usage (function-based views):

    from users.permissions import role_required
    from users.models import User

    @role_required(User.SUPER_ADMIN, User.ORGANIZER)
    def some_view(request):
        ...

Usage (class-based views):

    from users.permissions import RoleRequiredMixin
    from users.models import User

    class SomeView(RoleRequiredMixin, View):
        allowed_roles = (User.SUPER_ADMIN, User.STAFF)
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse


def _has_role(user, allowed_roles):
    if not user.is_authenticated:
        return False
    # Superusers (Django admin / `createsuperuser`) always pass role
    # checks so ops/dev staff are never locked out of their own system.
    if user.is_superuser:
        return True
    return user.role in allowed_roles


def role_required(*allowed_roles, redirect_url='dashboard:dashboard'):
    """Function-view decorator restricting access to specific roles.

    Unauthenticated users are sent to login (like @login_required).
    Authenticated users without a matching role are redirected back
    with an error message rather than getting a raw 403, since most
    of these views are reached via in-app navigation.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not _has_role(request.user, allowed_roles):
                messages.error(request, "You don't have permission to access that page.")
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def role_required_api(*allowed_roles):
    """Same as role_required but raises PermissionDenied (403) instead of
    redirecting — for API / JSON endpoints where a redirect makes no sense.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not _has_role(request.user, allowed_roles):
                raise PermissionDenied("You don't have permission to perform this action.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


class RoleRequiredMixin:
    """Class-based-view mixin restricting access to `allowed_roles`."""

    allowed_roles = ()
    permission_redirect_url = 'dashboard:dashboard'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('users:login')}?next={request.path}")
        if not _has_role(request.user, self.allowed_roles):
            messages.error(request, "You don't have permission to access that page.")
            return redirect(self.permission_redirect_url)
        return super().dispatch(request, *args, **kwargs)


# --- Ownership-aware helpers ------------------------------------------------
#
# `role_required` above only answers "can this role reach this *view* at
# all" — it can't know whether an Organizer owns the specific object they're
# about to edit/delete. Every "catalog" app (Category, Venue, Sponsor,
# StaffProfile, VendorProfile, Resource, ...) already carries a
# `created_by`-style owner FK for exactly this reason. The helpers below
# give every one of those apps a single, consistent way to answer "can this
# user manage *this* object", instead of each app re-implementing its own
# `_can_manage_x` ownership check (which is how these apps diverged and
# left Organizer locked out in the first place).
#
# Rule, matching the rest of the project's existing per-event pattern
# (see e.g. budget/views.py:_can_manage_budget):
#   - Super Admin (role or is_superuser): always allowed — full platform
#     access.
#   - Staff: allowed by default. Staff already had full, unrestricted
#     access to these catalogs before this change; `staff_unrestricted`
#     exists so a future app can opt out of that if it ever needs to scope
#     Staff too, without touching this helper's default behaviour.
#   - Organizer: allowed only for objects *they created* — an Organizer
#     never gets another Organizer's data this way.
#   - Everyone else (Vendor, Volunteer, Participant): denied.
def can_manage_catalog_item(user, obj, owner_field='created_by', staff_unrestricted=True):
    """Ownership check for shared catalog-style resources that aren't
    scoped to a single event (Category, Venue, Sponsor, StaffProfile,
    VendorProfile, Resource, ...) but do carry an owner FK.
    """
    if not user.is_authenticated:
        return False
    if user.is_super_admin:
        return True
    if staff_unrestricted and user.is_staff_role:
        return True
    if user.role == user.ORGANIZER:
        owner_id = getattr(obj, f"{owner_field}_id", None)
        return owner_id is not None and owner_id == user.id
    return False


def can_manage_event_scoped_item(user, event, staff_unrestricted=True):
    """Ownership check for objects that hang off a specific Event
    (mirrors budget/views.py:_can_manage_budget). An Organizer may manage
    an item only if they organize the `event` it belongs to.
    """
    if not user.is_authenticated:
        return False
    if user.is_super_admin:
        return True
    if staff_unrestricted and user.is_staff_role:
        return True
    return user.role == user.ORGANIZER and event.organizer_id == user.id
