from django.urls import path

from . import views

app_name = 'categories'

urlpatterns = [
    path('', views.category_list, name='category_list'),
    path('add/', views.category_create, name='category_create'),
    path('<slug:slug>/edit/', views.category_update, name='category_update'),
    path('<slug:slug>/delete/', views.category_delete, name='category_delete'),
]
