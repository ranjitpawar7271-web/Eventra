"""Eventra root URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('event_management.pages_urls')),
    path('accounts/', include('users.urls')),
    path('events/', include('events.urls')),
    path('categories/', include('categories.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('venues/', include('venues.urls')),
    path('resources/', include('resources.urls')),
    path('vendors/', include('vendors.urls')),
    path('staff/', include('staff.urls')),
    path('budget/', include('budget.urls')),
    path('tickets/', include('tickets.urls')),
    path('payments/', include('payments.urls')),
    path('reviews/', include('reviews.urls')),
    path('chatbot/', include('chatbot.urls')),
    path('reports/', include('reports.urls')),
    path('workflow/', include('workflow.urls')),
    path('sponsors/', include('sponsors.urls')),
    path('wishlist/', include('wishlist.urls')),
    path('tasks/', include('tasks.urls')),
    path('certificates/', include('certificates.urls')),
    path('surveys/', include('surveys.urls')),
    path('chat/', include('chat.urls')),
    path('gallery/', include('gallery.urls')),
    path('support/', include('support.urls')),
    path('currency/', include('currency.urls')),
    path('ops/', include('ops.urls')),
    path('organizations/', include('organizations.urls')),
    path('settings/', include('platform_settings.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')

handler404 = 'event_management.views.error_404'
handler403 = 'event_management.views.error_403'
handler500 = 'event_management.views.error_500'
