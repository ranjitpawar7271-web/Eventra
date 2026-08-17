import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from users.models import User
from users.permissions import can_manage_catalog_item, role_required
from .forms import MaintenanceScheduleForm, VenueBookingForm, VenueForm
from .models import MaintenanceSchedule, Venue, VenueBooking

# Organizer can now create/manage venues too; object-level edit/delete is
# further scoped to venues they created via can_manage_catalog_item, so an
# Organizer can't touch another Organizer's venue. Super Admin/Staff keep
# their existing unrestricted access.
VENUE_MANAGER_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)


def venue_list(request):
    venues = Venue.objects.filter(is_active=True)

    query = request.GET.get('q', '').strip()
    city = request.GET.get('city', '')
    min_capacity = request.GET.get('min_capacity', '')

    if query:
        venues = venues.filter(Q(name__icontains=query) | Q(address__icontains=query))
    if city:
        venues = venues.filter(city__iexact=city)
    if min_capacity.isdigit():
        venues = venues.filter(capacity__gte=int(min_capacity))

    paginator = Paginator(venues.order_by('name'), 9)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'query': query,
        'selected_city': city,
        'min_capacity': min_capacity,
        'cities': Venue.objects.filter(is_active=True).values_list('city', flat=True).distinct().order_by('city'),
        'can_manage_venues': request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in VENUE_MANAGER_ROLES
        ),
    }
    return render(request, 'venues/venue_list.html', context)
# Note: `can_manage_venues` above gates the "Add Venue" call-to-action
# (a role-level check — anyone in VENUE_MANAGER_ROLES may create one).
# Per-venue Edit/Delete visibility uses the `can_manage_catalog_item`
# template filter instead, since that's ownership-aware (see venue_detail).


def venue_detail(request, slug):
    venue = get_object_or_404(Venue, slug=slug)
    upcoming_bookings = venue.bookings.filter(status='confirmed').order_by('start_datetime')[:10]
    upcoming_maintenance = venue.maintenance_windows.order_by('start_datetime')[:10]
    context = {
        'venue': venue,
        'upcoming_bookings': upcoming_bookings,
        'upcoming_maintenance': upcoming_maintenance,
        'can_manage': can_manage_catalog_item(request.user, venue) if request.user.is_authenticated else False,
    }
    return render(request, 'venues/venue_detail.html', context)


@role_required(*VENUE_MANAGER_ROLES)
def venue_create(request):
    if request.method == 'POST':
        form = VenueForm(request.POST, request.FILES)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.created_by = request.user
            venue.save()
            messages.success(request, "Venue created successfully.")
            return redirect('venues:venue_detail', slug=venue.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VenueForm()
    return render(request, 'venues/venue_form.html', {'form': form, 'title': 'Add Venue'})


@login_required
def venue_update(request, slug):
    venue = get_object_or_404(Venue, slug=slug)
    if not can_manage_catalog_item(request.user, venue):
        messages.error(request, "You don't have permission to edit this venue.")
        return redirect('venues:venue_detail', slug=venue.slug)
    if request.method == 'POST':
        form = VenueForm(request.POST, request.FILES, instance=venue)
        if form.is_valid():
            form.save()
            messages.success(request, "Venue updated successfully.")
            return redirect('venues:venue_detail', slug=venue.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VenueForm(instance=venue)
    return render(request, 'venues/venue_form.html', {'form': form, 'title': 'Edit Venue', 'venue': venue})


@login_required
def venue_delete(request, slug):
    venue = get_object_or_404(Venue, slug=slug)
    if not can_manage_catalog_item(request.user, venue):
        messages.error(request, "You don't have permission to delete this venue.")
        return redirect('venues:venue_detail', slug=venue.slug)
    if request.method == 'POST':
        venue.delete()
        messages.success(request, "Venue deleted successfully.")
        return redirect('venues:venue_list')
    return render(request, 'venues/venue_confirm_delete.html', {'venue': venue})


@login_required
def venue_calendar(request, slug):
    """Simple month-view availability calendar for a venue."""
    venue = get_object_or_404(Venue, slug=slug)

    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except ValueError:
        year, month = today.year, today.month

    cal = calendar.Calendar(firstweekday=0)
    month_days = [d for d in cal.itermonthdates(year, month)]

    bookings = venue.bookings.filter(
        status='confirmed', start_datetime__year=year, start_datetime__month=month
    )
    maintenance = venue.maintenance_windows.filter(start_datetime__year=year, start_datetime__month=month)

    busy_days = {b.start_datetime.date() for b in bookings} | {m.start_datetime.date() for m in maintenance}

    weeks = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]

    prev_month = (month - 1) or 12
    prev_year = year - 1 if month == 1 else year
    next_month = (month % 12) + 1
    next_year = year + 1 if month == 12 else year

    context = {
        'venue': venue,
        'weeks': weeks,
        'current_month': date(year, month, 1),
        'busy_days': busy_days,
        'today': today,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'bookings': bookings.order_by('start_datetime'),
        'maintenance': maintenance.order_by('start_datetime'),
        'can_manage': can_manage_catalog_item(request.user, venue) if request.user.is_authenticated else False,
    }
    return render(request, 'venues/venue_calendar.html', context)


@login_required
def venue_booking_create(request, slug=None):
    initial = {}
    venue = None
    if slug:
        venue = get_object_or_404(Venue, slug=slug)
        initial['venue'] = venue

    if request.method == 'POST':
        form = VenueBookingForm(request.POST, initial=initial)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.booked_by = request.user
            booking.save()
            messages.success(request, "Venue booked successfully.")
            return redirect('venues:venue_detail', slug=booking.venue.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VenueBookingForm(initial=initial)
    return render(request, 'venues/venue_booking_form.html', {'form': form, 'venue': venue})


@login_required
def venue_booking_cancel(request, pk):
    booking = get_object_or_404(VenueBooking, pk=pk)
    # Booker can always cancel their own booking. Otherwise: Super
    # Admin/Staff (unrestricted), or the Organizer who organizes the
    # booking's linked event — NOT venue ownership, and NOT a blanket
    # Organizer bypass, since that would let any Organizer cancel any
    # other organizer's booking simply by being in VENUE_MANAGER_ROLES.
    is_privileged = request.user.is_super_admin or request.user.is_staff_role
    is_event_organizer = bool(
        booking.event_id and request.user.role == User.ORGANIZER
        and booking.event.organizer_id == request.user.id
    )
    if booking.booked_by != request.user and not (is_privileged or is_event_organizer):
        messages.error(request, "You are not authorized to cancel this booking.")
        return redirect('venues:venue_detail', slug=booking.venue.slug)

    if request.method == 'POST':
        booking.status = 'cancelled'
        booking.save()
        messages.success(request, "Booking cancelled.")
        return redirect('venues:venue_detail', slug=booking.venue.slug)
    return render(request, 'venues/venue_booking_confirm_cancel.html', {'booking': booking})


@login_required
def maintenance_create(request, slug):
    venue = get_object_or_404(Venue, slug=slug)
    if not can_manage_catalog_item(request.user, venue):
        messages.error(request, "You don't have permission to schedule maintenance for this venue.")
        return redirect('venues:venue_calendar', slug=venue.slug)
    if request.method == 'POST':
        form = MaintenanceScheduleForm(request.POST, initial={'venue': venue})
        if form.is_valid():
            maintenance = form.save(commit=False)
            maintenance.created_by = request.user
            maintenance.save()
            messages.success(request, "Maintenance window scheduled.")
            return redirect('venues:venue_calendar', slug=venue.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = MaintenanceScheduleForm(initial={'venue': venue})
    return render(request, 'venues/maintenance_form.html', {'form': form, 'venue': venue})


@login_required
def maintenance_delete(request, pk):
    maintenance = get_object_or_404(MaintenanceSchedule, pk=pk)
    slug = maintenance.venue.slug
    if not can_manage_catalog_item(request.user, maintenance.venue):
        messages.error(request, "You don't have permission to remove this maintenance window.")
        return redirect('venues:venue_calendar', slug=slug)
    if request.method == 'POST':
        maintenance.delete()
        messages.success(request, "Maintenance window removed.")
    return redirect('venues:venue_calendar', slug=slug)
