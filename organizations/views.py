from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from users.models import User
from .forms import MembershipForm, OrganizationForm
from .models import Organization, OrganizationMembership


def _membership(user, org):
    if not user.is_authenticated:
        return None
    return OrganizationMembership.objects.filter(organization=org, user=user).first()


def _is_org_owner(user, org):
    if not user.is_authenticated:
        return False
    if user.is_super_admin:
        return True
    m = _membership(user, org)
    return bool(m and m.role == OrganizationMembership.ROLE_OWNER)


def _is_org_manager(user, org):
    """Owner, Admin, or Super Admin — can edit org details and manage
    members (add/remove, promote up to Admin). Deleting the org or
    granting Owner requires `_is_org_owner` (Super Admin or the org's
    own Owner), not just any manager — see MembershipForm's
    restrict_to_non_owner flag for where that boundary is enforced."""
    if not user.is_authenticated:
        return False
    if user.is_super_admin:
        return True
    m = _membership(user, org)
    return bool(m and m.role in (OrganizationMembership.ROLE_OWNER, OrganizationMembership.ROLE_ADMIN))


def _is_org_member(user, org):
    if not user.is_authenticated:
        return False
    if user.is_super_admin:
        return True
    return _membership(user, org) is not None


@login_required
def organization_list(request):
    if request.user.is_super_admin:
        organizations = Organization.objects.all()
    else:
        organizations = Organization.objects.filter(memberships__user=request.user).distinct()
    return render(request, 'organizations/organization_list.html', {'organizations': organizations})


@login_required
def organization_create(request):
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can create organizations.")
        return redirect('organizations:organization_list')

    if request.method == 'POST':
        form = OrganizationForm(request.POST)
        if form.is_valid():
            org = form.save(commit=False)
            org.created_by = request.user
            org.save()
            OrganizationMembership.objects.create(organization=org, user=request.user, role=OrganizationMembership.ROLE_OWNER)
            messages.success(request, f"Organization '{org.name}' created.")
            return redirect('organizations:organization_detail', slug=org.slug)
    else:
        form = OrganizationForm()
    return render(request, 'organizations/organization_form.html', {'form': form, 'is_edit': False})


@login_required
def organization_detail(request, slug):
    org = get_object_or_404(Organization, slug=slug)
    if not _is_org_member(request.user, org):
        messages.error(request, "You're not a member of this organization.")
        return redirect('organizations:organization_list')

    context = {
        'organization': org,
        'memberships': org.memberships.select_related('user'),
        'events': org.events.all()[:10],
        'can_manage': _is_org_manager(request.user, org),
        'is_owner_level': _is_org_owner(request.user, org),
        'member_form': MembershipForm(restrict_to_non_owner=not _is_org_owner(request.user, org)),
    }
    return render(request, 'organizations/organization_detail.html', context)


@login_required
def organization_edit(request, slug):
    org = get_object_or_404(Organization, slug=slug)
    if not _is_org_manager(request.user, org):
        messages.error(request, "You don't have permission to edit this organization.")
        return redirect('organizations:organization_detail', slug=org.slug)

    if request.method == 'POST':
        form = OrganizationForm(request.POST, instance=org)
        if form.is_valid():
            form.save()
            messages.success(request, "Organization updated.")
            return redirect('organizations:organization_detail', slug=org.slug)
    else:
        form = OrganizationForm(instance=org)
    return render(request, 'organizations/organization_form.html', {'form': form, 'is_edit': True, 'organization': org})


@login_required
def organization_delete(request, slug):
    org = get_object_or_404(Organization, slug=slug)
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can delete organizations.")
        return redirect('organizations:organization_detail', slug=org.slug)

    if request.method == 'POST':
        name = org.name
        org.delete()
        messages.success(request, f"Organization '{name}' deleted. Events that belonged to it are unaffected — they just no longer have an organization.")
        return redirect('organizations:organization_list')
    return render(request, 'organizations/organization_confirm_delete.html', {'organization': org})


@login_required
def membership_add(request, slug):
    org = get_object_or_404(Organization, slug=slug)
    if not _is_org_manager(request.user, org):
        messages.error(request, "You don't have permission to manage members here.")
        return redirect('organizations:organization_detail', slug=org.slug)

    is_owner_level = _is_org_owner(request.user, org)
    if request.method == 'POST':
        form = MembershipForm(request.POST, restrict_to_non_owner=not is_owner_level)
        if form.is_valid():
            user = User.objects.get(username=form.cleaned_data['username'])
            role = form.cleaned_data['role']
            if role == OrganizationMembership.ROLE_OWNER and not is_owner_level:
                messages.error(request, "Only an Owner or Super Admin can grant Owner.")
                return redirect('organizations:organization_detail', slug=org.slug)
            OrganizationMembership.objects.update_or_create(
                organization=org, user=user, defaults={'role': role}
            )
            messages.success(request, f"{user.username} added as {role}.")
        else:
            for error in form.errors.get('username', []):
                messages.error(request, error)
    return redirect('organizations:organization_detail', slug=org.slug)


@login_required
def membership_remove(request, pk):
    membership = get_object_or_404(OrganizationMembership, pk=pk)
    org = membership.organization
    if not _is_org_manager(request.user, org):
        messages.error(request, "You don't have permission to manage members here.")
        return redirect('organizations:organization_detail', slug=org.slug)
    if membership.role == OrganizationMembership.ROLE_OWNER and not _is_org_owner(request.user, org):
        messages.error(request, "Only an Owner or Super Admin can remove an Owner.")
        return redirect('organizations:organization_detail', slug=org.slug)

    if request.method == 'POST':
        membership.delete()
        messages.success(request, "Member removed.")
    return redirect('organizations:organization_detail', slug=org.slug)
