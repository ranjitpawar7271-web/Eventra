from django.urls import path

from . import views

app_name = 'events'

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('create/', views.event_create, name='event_create'),
    path('create/start/', views.event_create_start, name='event_create_start'),
    path('my-events/', views.my_events, name='my_events'),
    path('my-registrations/', views.my_registrations, name='my_registrations'),
    path('<slug:slug>/', views.event_detail, name='event_detail'),
    path('<slug:slug>/registration-qr/', views.event_registration_qr, name='event_registration_qr'),
    path('<slug:slug>/calendar.ics', views.event_ics, name='event_ics'),
    path('<slug:slug>/edit/', views.event_update, name='event_update'),
    path('<slug:slug>/delete/', views.event_delete, name='event_delete'),
    path('<slug:slug>/participants/', views.event_participants, name='event_participants'),
    path('<slug:slug>/participants/export/', views.event_participants_export, name='event_participants_export'),
    path('<slug:slug>/register/', views.event_register, name='event_register'),
    path('<slug:slug>/cancel/', views.event_cancel_registration, name='event_cancel_registration'),
    path('<slug:slug>/waitlist/join/', views.join_waitlist, name='join_waitlist'),
    path('<slug:slug>/waitlist/leave/', views.leave_waitlist, name='leave_waitlist'),
    path('<slug:slug>/waitlist/', views.event_waitlist_manage, name='waitlist_manage'),
]