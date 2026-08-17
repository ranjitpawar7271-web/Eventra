from django.urls import path

from . import views

app_name = 'support'

urlpatterns = [
    path('faq/', views.faq_list, name='faq_list'),
    path('faq/add/', views.faq_create, name='faq_create'),
    path('faq/<int:pk>/edit/', views.faq_edit, name='faq_edit'),
    path('faq/<int:pk>/delete/', views.faq_delete, name='faq_delete'),

    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/add/', views.announcement_create, name='announcement_create'),
    path('announcements/<int:pk>/edit/', views.announcement_edit, name='announcement_edit'),
    path('announcements/<int:pk>/delete/', views.announcement_delete, name='announcement_delete'),

    path('contact/', views.support_contact, name='support_contact'),
    path('my-requests/', views.my_support_requests, name='my_support_requests'),
    path('inbox/', views.support_inbox, name='support_inbox'),
    path('inbox/<int:pk>/status/', views.support_request_status_update, name='support_request_status_update'),
]
