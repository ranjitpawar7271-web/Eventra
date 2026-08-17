from django.urls import path

from . import views

app_name = 'platform_settings'

urlpatterns = [
    path('', views.settings_edit, name='settings_edit'),
]
