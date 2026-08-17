from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from events.models import Event, Registration
from users.models import User
from .forms import PhotoUploadForm
from .models import Photo


def _can_manage(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


def _can_upload(user, event):
    """Confirmed registrants and managers — crowd-sourced from people who
    were actually part of the event, same audience rule used by chat and
    surveys."""
    if not user.is_authenticated:
        return False
    if _can_manage(user, event):
        return True
    return Registration.objects.filter(event=event, user=user, status='confirmed').exists()


def event_gallery(request, event_slug):
    """Public — matches events.views.event_detail, which has no login
    requirement either."""
    event = get_object_or_404(Event, slug=event_slug)
    photos = event.photos.select_related('uploaded_by')

    show_highlights_only = request.GET.get('filter') == 'highlights'
    if show_highlights_only:
        photos = photos.filter(is_highlight=True)

    context = {
        'event': event,
        'photos': photos,
        'show_highlights_only': show_highlights_only,
        'can_upload': _can_upload(request.user, event),
        'can_manage': _can_manage(request.user, event),
        'form': PhotoUploadForm(),
    }
    return render(request, 'gallery/event_gallery.html', context)


@login_required
@require_POST
def photo_upload(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_upload(request.user, event):
        messages.error(request, "Only registered attendees and organizers can add photos to this event's gallery.")
        return redirect('gallery:event_gallery', event_slug=event.slug)

    form = PhotoUploadForm(request.POST, request.FILES)
    if form.is_valid():
        photo = form.save(commit=False)
        photo.event = event
        photo.uploaded_by = request.user
        photo.save()
        messages.success(request, "Photo added to the gallery.")
    else:
        messages.error(request, "Couldn't upload that photo — check the file and try again.")
    return redirect('gallery:event_gallery', event_slug=event.slug)


@login_required
@require_POST
def photo_toggle_highlight(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    if not _can_manage(request.user, photo.event):
        messages.error(request, "You don't have permission to curate highlights for this event.")
        return redirect('gallery:event_gallery', event_slug=photo.event.slug)

    photo.is_highlight = not photo.is_highlight
    photo.save(update_fields=['is_highlight'])
    return redirect('gallery:event_gallery', event_slug=photo.event.slug)


@login_required
@require_POST
def photo_delete(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    if not (_can_manage(request.user, photo.event) or photo.uploaded_by_id == request.user.id):
        messages.error(request, "You don't have permission to delete this photo.")
        return redirect('gallery:event_gallery', event_slug=photo.event.slug)

    event_slug = photo.event.slug
    photo.delete()
    messages.success(request, "Photo removed.")
    return redirect('gallery:event_gallery', event_slug=event_slug)
