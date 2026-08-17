from django.urls import path

from . import views

app_name = 'venues'

urlpatterns = [
    path('', views.venue_list, name='venue_list'),
    path('add/', views.venue_create, name='venue_create'),
    path('book/', views.venue_booking_create, name='venue_booking_create'),
    path('booking/<int:pk>/cancel/', views.venue_booking_cancel, name='venue_booking_cancel'),
    path('maintenance/<int:pk>/delete/', views.maintenance_delete, name='maintenance_delete'),
    path('<slug:slug>/', views.venue_detail, name='venue_detail'),
    path('<slug:slug>/edit/', views.venue_update, name='venue_update'),
    path('<slug:slug>/delete/', views.venue_delete, name='venue_delete'),
    path('<slug:slug>/calendar/', views.venue_calendar, name='venue_calendar'),
    path('<slug:slug>/book/', views.venue_booking_create, name='venue_booking_create_for'),
    path('<slug:slug>/maintenance/add/', views.maintenance_create, name='maintenance_create'),
]
