from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from events.models import Event
from users.models import User
from users.permissions import can_manage_catalog_item, role_required
from .forms import EventSponsorshipForm, EventSponsorshipStatusForm, SponsorForm
from .models import EventSponsorship, Sponsor

# Sponsor *catalog* management (creating/editing/deleting a sponsoring
# company) is now open to Organizer as well as Super Admin, scoped to the
# sponsors they created (see can_manage_catalog_item) — matching the same
# "shared catalog with owner FK" pattern venues/categories/resources use.
# Staff never had catalog access here; that's unchanged. Attaching an
# existing sponsor to a specific event (a "deal") follows the same
# organizer-owns-their-event-or-staff/admin pattern Module 6 (Budget) uses
# for expenses/revenue, since it's really a budget-adjacent action.
SPONSOR_CATALOG_ROLES = (User.SUPER_ADMIN, User.ORGANIZER)
DEAL_STATUS_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)


def _can_browse_catalog(user):
    return user.is_authenticated and (user.is_superuser or user.can_manage_events)


def _can_manage_deal(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


@login_required
def sponsor_list(request):
    if not _can_browse_catalog(request.user):
        messages.error(request, "You don't have permission to view the sponsor catalog.")
        return redirect('dashboard:dashboard')

    sponsors = Sponsor.objects.all()
    can_manage_catalog = request.user.is_super_admin or request.user.role in SPONSOR_CATALOG_ROLES
    if not can_manage_catalog:
        sponsors = sponsors.filter(is_active=True)

    query = request.GET.get('q', '').strip()
    if query:
        sponsors = sponsors.filter(
            Q(company_name__icontains=query) | Q(description__icontains=query)
        )

    paginator = Paginator(sponsors, 9)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'query': query,
        'can_manage_catalog': can_manage_catalog,
    }
    return render(request, 'sponsors/sponsor_list.html', context)


@login_required
def sponsor_detail(request, slug):
    if not _can_browse_catalog(request.user):
        messages.error(request, "You don't have permission to view this sponsor.")
        return redirect('dashboard:dashboard')

    sponsor = get_object_or_404(Sponsor, slug=slug)
    can_manage_catalog = request.user.is_super_admin or request.user.role in SPONSOR_CATALOG_ROLES

    if not sponsor.is_active and not can_manage_catalog:
        messages.error(request, "This sponsor is no longer active.")
        return redirect('sponsors:sponsor_list')

    context = {
        'sponsor': sponsor,
        'sponsorships': sponsor.sponsorships.select_related('event').all(),
        'can_manage_catalog': can_manage_catalog,
        'can_manage_this_sponsor': can_manage_catalog_item(request.user, sponsor, staff_unrestricted=False),
    }
    return render(request, 'sponsors/sponsor_detail.html', context)


@role_required(*SPONSOR_CATALOG_ROLES)
def sponsor_create(request):
    if request.method == 'POST':
        form = SponsorForm(request.POST, request.FILES)
        if form.is_valid():
            sponsor = form.save(commit=False)
            sponsor.created_by = request.user
            sponsor.save()
            messages.success(request, f"Sponsor '{sponsor.company_name}' added.")
            return redirect('sponsors:sponsor_detail', slug=sponsor.slug)
    else:
        form = SponsorForm()
    return render(request, 'sponsors/sponsor_form.html', {'form': form, 'is_edit': False})


@login_required
def sponsor_edit(request, slug):
    sponsor = get_object_or_404(Sponsor, slug=slug)
    if not can_manage_catalog_item(request.user, sponsor, staff_unrestricted=False):
        messages.error(request, "You don't have permission to edit this sponsor.")
        return redirect('sponsors:sponsor_detail', slug=sponsor.slug)
    if request.method == 'POST':
        form = SponsorForm(request.POST, request.FILES, instance=sponsor)
        if form.is_valid():
            form.save()
            messages.success(request, f"Sponsor '{sponsor.company_name}' updated.")
            return redirect('sponsors:sponsor_detail', slug=sponsor.slug)
    else:
        form = SponsorForm(instance=sponsor)
    return render(request, 'sponsors/sponsor_form.html', {'form': form, 'is_edit': True, 'sponsor': sponsor})


@login_required
def sponsor_delete(request, slug):
    sponsor = get_object_or_404(Sponsor, slug=slug)
    if not can_manage_catalog_item(request.user, sponsor, staff_unrestricted=False):
        messages.error(request, "You don't have permission to delete this sponsor.")
        return redirect('sponsors:sponsor_detail', slug=sponsor.slug)
    if request.method == 'POST':
        name = sponsor.company_name
        sponsor.delete()
        messages.success(request, f"Sponsor '{name}' removed.")
        return redirect('sponsors:sponsor_list')
    return render(request, 'sponsors/sponsor_confirm_delete.html', {'sponsor': sponsor})


@login_required
def event_sponsorship_create(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_manage_deal(request.user, event):
        messages.error(request, "You don't have permission to manage sponsorships for this event.")
        return redirect('events:event_detail', slug=event.slug)

    if not Sponsor.objects.filter(is_active=True).exists():
        messages.info(request, "No active sponsors in the catalog yet. Ask a Super Admin to add one first.")

    if request.method == 'POST':
        form = EventSponsorshipForm(request.POST)
        if form.is_valid():
            deal = form.save(commit=False)
            deal.event = event
            deal.created_by = request.user
            deal.save()
            messages.success(request, f"Sponsorship with {deal.sponsor.company_name} added.")
            return redirect('events:event_detail', slug=event.slug)
    else:
        form = EventSponsorshipForm()

    return render(request, 'sponsors/sponsorship_form.html', {'form': form, 'event': event})


@login_required
def event_sponsorship_status_update(request, pk):
    deal = get_object_or_404(EventSponsorship, pk=pk)
    if not _can_manage_deal(request.user, deal.event):
        messages.error(request, "You don't have permission to update this sponsorship.")
        return redirect('events:event_detail', slug=deal.event.slug)
    if request.method == 'POST':
        form = EventSponsorshipStatusForm(request.POST, instance=deal)
        if form.is_valid():
            form.save()
            messages.success(request, f"Sponsorship status updated to {deal.get_status_display()}.")
    return redirect('events:event_detail', slug=deal.event.slug)


@login_required
def event_sponsorship_delete(request, pk):
    deal = get_object_or_404(EventSponsorship, pk=pk)
    if not _can_manage_deal(request.user, deal.event):
        messages.error(request, "You don't have permission to remove this sponsorship.")
        return redirect('events:event_detail', slug=deal.event.slug)

    if request.method == 'POST':
        event_slug = deal.event.slug
        deal.delete()
        messages.success(request, "Sponsorship removed.")
        return redirect('events:event_detail', slug=event_slug)
    return render(request, 'sponsors/sponsorship_confirm_delete.html', {'deal': deal})
