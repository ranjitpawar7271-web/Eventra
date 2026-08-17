from django.urls import path

from . import views

app_name = 'certificates'

urlpatterns = [
    path('', views.my_certificates, name='my_certificates'),
    path('verify/<str:token>/', views.verify, name='verify'),
    path('events/<slug:event_slug>/', views.certificate_hub, name='certificate_hub'),
    path('events/<slug:event_slug>/bulk-issue/', views.certificate_bulk_issue, name='certificate_bulk_issue'),
    path('tickets/<str:ticket_code>/issue/', views.certificate_issue, name='certificate_issue'),
    path('<str:certificate_code>/', views.certificate_detail, name='certificate_detail'),
    path('<str:certificate_code>/qr/', views.certificate_qr_image, name='certificate_qr'),
    path('<str:certificate_code>/pdf/', views.certificate_pdf, name='certificate_pdf'),
]
