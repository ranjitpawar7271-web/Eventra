from django.urls import path

from . import views

app_name = 'ops'

urlpatterns = [
    path('', views.system_health, name='system_health'),
    path('backup/', views.backup_create, name='backup_create'),
    path('restore/', views.restore_upload, name='restore_upload'),
]
