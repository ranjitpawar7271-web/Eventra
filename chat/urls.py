from django.urls import path

from . import views

app_name = 'chat'

urlpatterns = [
    path('events/<slug:event_slug>/', views.event_chat, name='event_chat'),
    path('events/<slug:event_slug>/post/', views.message_post, name='message_post'),
    path('events/<slug:event_slug>/poll/', views.message_poll, name='message_poll'),
    path('messages/<int:pk>/delete/', views.message_delete, name='message_delete'),
]
