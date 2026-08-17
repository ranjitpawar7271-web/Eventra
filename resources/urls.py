from django.urls import path

from . import views

app_name = 'resources'

urlpatterns = [
    path('', views.resource_list, name='resource_list'),
    path('add/', views.resource_create, name='resource_create'),
    path('allocate/', views.resource_allocate, name='resource_allocate'),
    path('allocation/<int:pk>/return/', views.resource_allocation_return, name='resource_allocation_return'),
    path('allocation/<int:pk>/cancel/', views.resource_allocation_cancel, name='resource_allocation_cancel'),
    path('damage-reports/', views.damage_report_list, name='damage_report_list'),
    path('damage-reports/report/', views.damage_report_create, name='damage_report_create'),
    path('damage-reports/<int:pk>/resolve/', views.damage_report_resolve, name='damage_report_resolve'),
    path('<slug:slug>/', views.resource_detail, name='resource_detail'),
    path('<slug:slug>/edit/', views.resource_update, name='resource_update'),
    path('<slug:slug>/delete/', views.resource_delete, name='resource_delete'),
    path('<slug:slug>/allocate/', views.resource_allocate, name='resource_allocate_for'),
    path('<slug:slug>/report-damage/', views.damage_report_create, name='damage_report_create_for'),
]
