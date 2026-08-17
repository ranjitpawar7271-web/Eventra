from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from events.models import Event
from .models import FavoriteEvent


@login_required
def wishlist_list(request):
    favorites = FavoriteEvent.objects.filter(user=request.user).select_related(
        'event', 'event__category', 'event__organizer'
    )
    context = {'favorites': favorites}
    return render(request, 'wishlist/wishlist_list.html', context)


@login_required
@require_POST
def toggle_favorite(request, slug):
    event = get_object_or_404(Event, slug=slug)
    favorite, created = FavoriteEvent.objects.get_or_create(user=request.user, event=event)
    if not created:
        favorite.delete()
        is_favorited = False
    else:
        is_favorited = True

    # Support both a plain form POST (redirect back to wherever the button
    # was clicked from) and a fetch()-based AJAX toggle (JSON response),
    # so the same endpoint works whether or not JS is used on the page.
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'is_favorited': is_favorited, 'event': event.slug})

    if is_favorited:
        messages.success(request, f"Added \"{event.title}\" to your wishlist.")
    else:
        messages.info(request, f"Removed \"{event.title}\" from your wishlist.")

    next_url = request.POST.get('next') or reverse('events:event_detail', kwargs={'slug': event.slug})
    return redirect(next_url)
