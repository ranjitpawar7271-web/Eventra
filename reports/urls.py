from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_hub, name='report_hub'),
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('<str:report_type>/', views.report_view, name='report'),
    path('<str:report_type>/event/<slug:slug>/', views.report_view, name='report_for_event'),
]
