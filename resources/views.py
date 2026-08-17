from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from users.models import User
from users.permissions import can_manage_catalog_item, role_required
from .forms import DamageReportForm, ResourceAllocationForm, ResourceForm
from .models import DamageReport, Resource, ResourceAllocation

# Resource is a shared inventory catalog with a `created_by` owner FK
# (same pattern as Venue). Organizer can now build and manage their own
# corner of the catalog; Super Admin/Staff keep unrestricted access.
RESOURCE_MANAGER_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)
# Who's allowed to draw from the resource pool for an event.
RESOURCE_ALLOCATOR_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)


def _can_manage(user):
    """Role-level check — used only for gating list-wide views (create
    button visibility, damage-report queue access). Per-object edit/
    delete/resolve actions use can_manage_catalog_item instead, so an
    Organizer only touches resources they actually created."""
    return user.is_authenticated and (user.is_superuser or user.role in RESOURCE_MANAGER_ROLES)


def resource_list(request):
    resources = Resource.objects.filter(is_active=True)

    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')

    if query:
        resources = resources.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category:
        resources = resources.filter(category=category)

    paginator = Paginator(resources, 9)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'query': query,
        'selected_category': category,
        'categories': Resource.CATEGORY_CHOICES,
        'can_manage_resources': _can_manage(request.user),
    }
    return render(request, 'resources/resource_list.html', context)


def resource_detail(request, slug):
    resource = get_object_or_404(Resource, slug=slug)
    upcoming_allocations = resource.allocations.filter(
        status='allocated', end_datetime__gte=timezone.now()
    ).order_by('start_datetime')[:10]
    open_damage_reports = resource.damage_reports.exclude(status='resolved').order_by('-created_at')
    context = {
        'resource': resource,
        'upcoming_allocations': upcoming_allocations,
        'open_damage_reports': open_damage_reports,
        'can_manage': can_manage_catalog_item(request.user, resource) if request.user.is_authenticated else False,
    }
    return render(request, 'resources/resource_detail.html', context)


@role_required(*RESOURCE_MANAGER_ROLES)
def resource_create(request):
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.created_by = request.user
            resource.save()
            messages.success(request, "Resource added to inventory.")
            return redirect('resources:resource_detail', slug=resource.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ResourceForm()
    return render(request, 'resources/resource_form.html', {'form': form, 'title': 'Add Resource'})


@login_required
def resource_update(request, slug):
    resource = get_object_or_404(Resource, slug=slug)
    if not can_manage_catalog_item(request.user, resource):
        messages.error(request, "You don't have permission to edit this resource.")
        return redirect('resources:resource_detail', slug=resource.slug)
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            form.save()
            messages.success(request, "Resource updated successfully.")
            return redirect('resources:resource_detail', slug=resource.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ResourceForm(instance=resource)
    return render(request, 'resources/resource_form.html', {'form': form, 'title': 'Edit Resource', 'resource': resource})


@login_required
def resource_delete(request, slug):
    resource = get_object_or_404(Resource, slug=slug)
    if not can_manage_catalog_item(request.user, resource):
        messages.error(request, "You don't have permission to delete this resource.")
        return redirect('resources:resource_detail', slug=resource.slug)
    if request.method == 'POST':
        resource.delete()
        messages.success(request, "Resource removed from inventory.")
        return redirect('resources:resource_list')
    return render(request, 'resources/resource_confirm_delete.html', {'resource': resource})


@role_required(*RESOURCE_ALLOCATOR_ROLES)
def resource_allocate(request, slug=None):
    initial = {}
    resource = None
    if slug:
        resource = get_object_or_404(Resource, slug=slug)
        initial['resource'] = resource

    if request.method == 'POST':
        form = ResourceAllocationForm(request.POST, initial=initial)
        if form.is_valid():
            allocation = form.save(commit=False)
            allocation.requested_by = request.user
            allocation.save()
            messages.success(request, f"Allocated {allocation.quantity} {allocation.resource.unit} of {allocation.resource.name}.")
            return redirect('resources:resource_detail', slug=allocation.resource.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ResourceAllocationForm(initial=initial)
    return render(request, 'resources/resource_allocation_form.html', {'form': form, 'resource': resource})


@login_required
def resource_allocation_return(request, pk):
    allocation = get_object_or_404(ResourceAllocation, pk=pk)
    if allocation.requested_by != request.user and not can_manage_catalog_item(request.user, allocation.resource):
        messages.error(request, "You are not authorized to return this allocation.")
        return redirect('resources:resource_detail', slug=allocation.resource.slug)

    if request.method == 'POST':
        allocation.mark_returned()
        messages.success(request, "Resource marked as returned.")
        return redirect('resources:resource_detail', slug=allocation.resource.slug)
    return render(request, 'resources/resource_allocation_confirm_return.html', {'allocation': allocation})


@login_required
def resource_allocation_cancel(request, pk):
    allocation = get_object_or_404(ResourceAllocation, pk=pk)
    if allocation.requested_by != request.user and not can_manage_catalog_item(request.user, allocation.resource):
        messages.error(request, "You are not authorized to cancel this allocation.")
        return redirect('resources:resource_detail', slug=allocation.resource.slug)

    if request.method == 'POST':
        allocation.status = 'cancelled'
        allocation.save()
        messages.success(request, "Allocation cancelled.")
        return redirect('resources:resource_detail', slug=allocation.resource.slug)
    return render(request, 'resources/resource_allocation_confirm_cancel.html', {'allocation': allocation})


@login_required
def damage_report_create(request, slug=None):
    resource = None
    if slug:
        resource = get_object_or_404(Resource, slug=slug)

    if request.method == 'POST':
        form = DamageReportForm(request.POST, resource=resource)
        if form.is_valid():
            report = form.save(commit=False)
            report.reported_by = request.user
            report.save()
            messages.success(request, "Damage report filed. Affected units are now marked out of service.")
            return redirect('resources:resource_detail', slug=report.resource.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = DamageReportForm(resource=resource)
    return render(request, 'resources/damage_report_form.html', {'form': form, 'resource': resource})


@login_required
def damage_report_resolve(request, pk):
    report = get_object_or_404(DamageReport, pk=pk)
    if not can_manage_catalog_item(request.user, report.resource):
        messages.error(request, "You don't have permission to resolve this damage report.")
        return redirect('resources:resource_detail', slug=report.resource.slug)
    if request.method == 'POST':
        report.resolve(resolved_by=request.user)
        messages.success(request, "Damage report resolved — units returned to the available pool.")
    return redirect('resources:resource_detail', slug=report.resource.slug)


@login_required
def damage_report_list(request):
    reports = DamageReport.objects.select_related('resource', 'reported_by').exclude(status='resolved')
    if not (request.user.is_super_admin or request.user.is_staff_role):
        if request.user.role != User.ORGANIZER:
            messages.error(request, "You don't have permission to view damage reports.")
            return redirect('dashboard:dashboard')
        reports = reports.filter(resource__created_by=request.user)
    return render(request, 'resources/damage_report_list.html', {'reports': reports})
