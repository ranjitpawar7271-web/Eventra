from django.urls import path

from . import views

app_name = 'tickets'

urlpatterns = [
    path('', views.my_tickets, name='my_tickets'),
    path('<str:ticket_code>/', views.ticket_detail, name='ticket_detail'),
    path('<str:ticket_code>/qr/', views.ticket_qr_image, name='ticket_qr'),
    path('<str:ticket_code>/pdf/', views.ticket_pdf, name='ticket_pdf'),
    path('<str:ticket_code>/type/', views.ticket_type_update, name='ticket_type_update'),
    path('<str:ticket_code>/status/', views.ticket_status_update, name='ticket_status_update'),

    path('events/<slug:slug>/scanner/', views.scanner_page, name='scanner'),
    path('events/<slug:slug>/scanner/checkin/', views.check_in, name='check_in'),
    path('events/<slug:slug>/scanner/checkout/', views.check_out, name='check_out'),
    path('events/<slug:slug>/attendance/', views.event_checkin_logs, name='checkin_logs'),
    path('events/<slug:slug>/attendance/stats.json', views.event_checkin_stats_json, name='checkin_stats_json'),
    path('events/<slug:slug>/attendance/export/', views.event_checkin_logs_export, name='checkin_logs_export'),
]
