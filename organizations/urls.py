from django.urls import path

from . import views

app_name = 'organizations'

urlpatterns = [
    path('', views.organization_list, name='organization_list'),
    path('add/', views.organization_create, name='organization_create'),
    path('<slug:slug>/', views.organization_detail, name='organization_detail'),
    path('<slug:slug>/edit/', views.organization_edit, name='organization_edit'),
    path('<slug:slug>/delete/', views.organization_delete, name='organization_delete'),
    path('<slug:slug>/members/add/', views.membership_add, name='membership_add'),
    path('members/<int:pk>/remove/', views.membership_remove, name='membership_remove'),
]
