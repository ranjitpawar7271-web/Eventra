from django.urls import path

from . import views

app_name = 'gallery'

urlpatterns = [
    path('events/<slug:event_slug>/', views.event_gallery, name='event_gallery'),
    path('events/<slug:event_slug>/upload/', views.photo_upload, name='photo_upload'),
    path('photos/<int:pk>/toggle-highlight/', views.photo_toggle_highlight, name='photo_toggle_highlight'),
    path('photos/<int:pk>/delete/', views.photo_delete, name='photo_delete'),
]
