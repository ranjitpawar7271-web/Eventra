from django.urls import path

from . import views

app_name = 'currency'

urlpatterns = [
    path('', views.currency_list, name='currency_list'),
    path('add/', views.currency_create, name='currency_create'),
    path('<int:pk>/edit/', views.currency_edit, name='currency_edit'),
    path('<int:pk>/delete/', views.currency_delete, name='currency_delete'),
    path('set/', views.set_display_currency, name='set_display_currency'),
]
