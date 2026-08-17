from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import date as date_filter
from django.views.decorators.http import require_POST

from events.models import Event, Registration
from users.models import User
from .models import Message

FEED_PAGE_SIZE = 100


def _can_manage(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


def _is_event_audience(user, event):
    """Managers, plus anyone with a confirmed registration — same rule as
    surveys.views._is_event_audience. An event's chat/announcements feed
    is for that event's actual audience, not the whole platform."""
    if not user.is_authenticated:
        return False
    if _can_manage(user, event):
        return True
    return Registration.objects.filter(event=event, user=user, status='confirmed').exists()


def _serialize(message):
    return {
        'id': message.id,
        'sender': message.sender.get_full_name() or message.sender.username,
        'sender_id': message.sender_id,
        'body': message.body,
        'message_type': message.message_type,
        'created_at': date_filter(message.created_at, 'M d, g:i A'),
    }


@login_required
def event_chat(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _is_event_audience(request.user, event):
        messages.error(request, "This event's chat is only available to registered attendees and organizers.")
        return redirect('events:event_detail', slug=event.slug)

    recent_messages = event.chat_messages.select_related('sender').order_by('-created_at')[:FEED_PAGE_SIZE]
    recent_messages = list(reversed(recent_messages))
    last_id = recent_messages[-1].id if recent_messages else 0

    context = {
        'event': event,
        'chat_messages': recent_messages,
        'can_manage': _can_manage(request.user, event),
        'last_id': last_id,
    }
    return render(request, 'chat/event_chat.html', context)


@login_required
@require_POST
def message_post(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _is_event_audience(request.user, event):
        return JsonResponse({'error': 'not permitted'}, status=403)

    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'error': 'empty message'}, status=400)

    requested_type = request.POST.get('message_type', Message.TYPE_CHAT)
    # Only a manager can post an announcement — anyone else's request for
    # message_type=announcement is silently downgraded to a normal chat
    # message rather than rejected outright, since the AJAX form always
    # submits *some* value for this field either way.
    message_type = requested_type if (requested_type == Message.TYPE_ANNOUNCEMENT and _can_manage(request.user, event)) else Message.TYPE_CHAT

    message = Message.objects.create(event=event, sender=request.user, body=body[:1000], message_type=message_type)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(_serialize(message))
    return redirect('chat:event_chat', event_slug=event.slug)


@login_required
def message_poll(request, event_slug):
    """Polling endpoint: returns any messages posted after `after` (a
    message id), newest last. The chat page's JS calls this on an
    interval — see the Message model docstring for why polling instead
    of a websocket push."""
    event = get_object_or_404(Event, slug=event_slug)
    if not _is_event_audience(request.user, event):
        return JsonResponse({'error': 'not permitted'}, status=403)

    after = request.GET.get('after', '0')
    try:
        after = int(after)
    except ValueError:
        after = 0

    new_messages = event.chat_messages.select_related('sender').filter(id__gt=after).order_by('created_at')
    return JsonResponse({'messages': [_serialize(m) for m in new_messages]})


@login_required
@require_POST
def message_delete(request, pk):
    message = get_object_or_404(Message, pk=pk)
    if not (_can_manage(request.user, message.event) or message.sender_id == request.user.id):
        messages.error(request, "You don't have permission to delete this message.")
        return redirect('chat:event_chat', event_slug=message.event.slug)

    event_slug = message.event.slug
    message.delete()
    return redirect('chat:event_chat', event_slug=event_slug)
