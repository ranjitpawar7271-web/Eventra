from django.urls import path

from . import views

app_name = 'vendors'

urlpatterns = [
    path('', views.vendor_list, name='vendor_list'),
    path('register/', views.vendor_profile_create, name='vendor_profile_create'),
    path('profile/edit/', views.vendor_profile_edit, name='vendor_profile_edit'),
    path('payments/', views.vendor_payment_list, name='vendor_payment_list'),
    path('services/<int:pk>/delete/', views.vendor_service_delete, name='vendor_service_delete'),
    path('documents/<int:pk>/delete/', views.vendor_document_delete, name='vendor_document_delete'),
    path('documents/<int:pk>/download/', views.vendor_document_download, name='vendor_document_download'),
    path('contracts/<int:pk>/', views.vendor_contract_detail, name='vendor_contract_detail'),
    path('contracts/<int:pk>/document/', views.vendor_contract_document_download, name='vendor_contract_document_download'),
    path('contracts/<int:pk>/status/', views.vendor_contract_update_status, name='vendor_contract_update_status'),
    path('contracts/<int:pk>/payments/add/', views.vendor_payment_create, name='vendor_payment_create'),
    path('<slug:slug>/', views.vendor_detail, name='vendor_detail'),
    path('<slug:slug>/approve/', views.vendor_approve, name='vendor_approve'),
    path('<slug:slug>/reject/', views.vendor_reject, name='vendor_reject'),
    path('<slug:slug>/suspend/', views.vendor_suspend, name='vendor_suspend'),
    path('<slug:slug>/services/add/', views.vendor_service_create, name='vendor_service_create'),
    path('<slug:slug>/documents/upload/', views.vendor_document_upload, name='vendor_document_upload'),
    path('<slug:slug>/contracts/create/', views.vendor_contract_create, name='vendor_contract_create'),
    path('<slug:slug>/rate/', views.vendor_rating_create, name='vendor_rating_create'),
]
