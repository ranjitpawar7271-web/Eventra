from django.urls import path

from . import views

app_name = 'budget'

urlpatterns = [
    path('', views.budget_list, name='budget_list'),
    path('expenses/<int:pk>/status/', views.expense_status_update, name='expense_status_update'),
    path('expenses/<int:pk>/receipt/', views.expense_receipt_download, name='expense_receipt_download'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('revenue/<int:pk>/delete/', views.revenue_delete, name='revenue_delete'),
    path('<slug:event_slug>/', views.budget_detail, name='budget_detail'),
    path('<slug:event_slug>/setup/', views.budget_setup, name='budget_setup'),
    path('<slug:event_slug>/expenses/add/', views.expense_create, name='expense_create'),
    path('<slug:event_slug>/revenue/add/', views.revenue_create, name='revenue_create'),
]
