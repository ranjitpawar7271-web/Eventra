from django.urls import path

from . import views

app_name = 'sponsors'

urlpatterns = [
    path('', views.sponsor_list, name='sponsor_list'),
    path('add/', views.sponsor_create, name='sponsor_create'),
    path('deals/<int:pk>/status/', views.event_sponsorship_status_update, name='event_sponsorship_status_update'),
    path('deals/<int:pk>/delete/', views.event_sponsorship_delete, name='event_sponsorship_delete'),
    path('events/<slug:event_slug>/add/', views.event_sponsorship_create, name='event_sponsorship_create'),
    path('<slug:slug>/', views.sponsor_detail, name='sponsor_detail'),
    path('<slug:slug>/edit/', views.sponsor_edit, name='sponsor_edit'),
    path('<slug:slug>/delete/', views.sponsor_delete, name='sponsor_delete'),
]
