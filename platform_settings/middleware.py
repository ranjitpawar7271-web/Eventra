from django.shortcuts import render

from .models import PlatformSettings

# Paths that stay reachable during maintenance mode regardless of role —
# without this, turning maintenance mode on could lock everyone
# (including a Super Admin trying to log in on a fresh session) out of
# the one page that turns it back off.
EXEMPT_PREFIXES = ('/admin/', '/accounts/login/', '/accounts/logout/', '/static/', '/media/')


class MaintenanceModeMiddleware:
    """Reads a single DB row (PlatformSettings) per request. Cheap
    (one indexed PK lookup) and always current — a Super Admin flipping
    the switch takes effect on the very next request, not after a
    process restart or cache TTL."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_block(request):
            return render(request, 'platform_settings/maintenance.html', {
                'message': PlatformSettings.load().maintenance_message,
            }, status=503)
        return self.get_response(request)

    def _should_block(self, request):
        if request.path.startswith(EXEMPT_PREFIXES):
            return False
        settings_obj = PlatformSettings.load()
        if not settings_obj.maintenance_mode:
            return False
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False) and getattr(user, 'is_super_admin', False):
            return False
        return True
