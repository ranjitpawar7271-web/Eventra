from .models import Notification


def notifications(request):
    """Powers the bell icon in the navbar on every page. Cheap for the
    common case (two small queries, only for logged-in users) rather than
    each view remembering to pass this in individually.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}

    user_notifications = Notification.objects.filter(user=request.user)
    return {
        'nav_notifications': user_notifications[:6],
        'nav_unread_count': user_notifications.filter(is_read=False).count(),
    }
