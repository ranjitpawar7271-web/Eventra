from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from events.models import Event, Registration
from tickets.models import Ticket
from .forms import ReviewForm
from .models import Review


def can_review(user, event):
    """A participant may review an event only once they've actually
    attended it or it has run its course — matches the spec's "only
    after attending/completing the event", checked two ways since not
    every event uses the QR check-in flow (e.g. a free virtual talk):
    either their ticket was scanned in, or the event's end time has
    passed for a confirmed registrant.
    """
    if not user.is_authenticated:
        return False
    registration = Registration.objects.filter(event=event, user=user, status='confirmed').first()
    if not registration:
        return False
    if Review.objects.filter(event=event, user=user).exists():
        return False
    attended = Ticket.objects.filter(registration=registration, status=Ticket.STATUS_CHECKED_IN).exists()
    return attended or event.has_ended or event.status == 'completed'


@login_required
def review_create(request, slug):
    event = get_object_or_404(Event, slug=slug)
    if not can_review(request.user, event):
        messages.error(request, "You can review this event after you've attended it or it has ended.")
        return redirect('events:event_detail', slug=slug)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.event = event
            review.user = request.user
            review.save()
            messages.success(request, "Thanks for your review!")
            return redirect('events:event_detail', slug=slug)
    else:
        form = ReviewForm()

    return render(request, 'reviews/review_form.html', {'event': event, 'form': form})


@login_required
def review_edit(request, pk):
    review = get_object_or_404(Review, pk=pk)
    if review.user_id != request.user.id:
        messages.error(request, "You can only edit your own review.")
        return redirect('events:event_detail', slug=review.event.slug)

    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Your review has been updated.")
            return redirect('events:event_detail', slug=review.event.slug)
    else:
        form = ReviewForm(instance=review)

    return render(request, 'reviews/review_form.html', {'event': review.event, 'form': form, 'review': review})


@login_required
@require_POST
def review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk)
    if review.user_id != request.user.id and not (request.user.is_super_admin or request.user.is_staff_role):
        messages.error(request, "You don't have permission to delete this review.")
        return redirect('events:event_detail', slug=review.event.slug)

    slug = review.event.slug
    review.delete()
    messages.success(request, "Review deleted.")
    return redirect('events:event_detail', slug=slug)


def event_reviews(request, slug):
    event = get_object_or_404(Event, slug=slug)
    reviews = event.reviews.select_related('user').all()
    return render(request, 'reviews/event_reviews.html', {'event': event, 'reviews': reviews})
