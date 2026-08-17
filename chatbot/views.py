from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from . import services

MAX_MESSAGE_LENGTH = 1000


@login_required
@require_POST
def send_message(request):
    message = (request.POST.get('message') or '').strip()

    if not message:
        return JsonResponse({'success': False, 'error': "Please type a message."}, status=400)
    if len(message) > MAX_MESSAGE_LENGTH:
        return JsonResponse(
            {'success': False, 'error': f"Message is too long (max {MAX_MESSAGE_LENGTH} characters)."},
            status=400,
        )

    if services.is_rate_limited(request.user):
        return JsonResponse(
            {'success': False, 'error': "You're sending messages too quickly. Please wait a moment and try again."},
            status=429,
        )

    try:
        reply = services.handle_message(request.user, message)
    except Exception:
        # Never leak a raw traceback to the widget — matches "Never
        # expose raw Django/Python errors to normal users."
        return JsonResponse(
            {'success': False, 'error': "Something went wrong on our end. Please try again in a moment."},
            status=500,
        )

    return JsonResponse({'success': True, 'reply': reply})
