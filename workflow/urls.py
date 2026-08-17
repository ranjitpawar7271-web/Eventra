from django.urls import path

from . import views

app_name = 'workflow'

urlpatterns = [
    path('approvals/', views.approval_list, name='approval_list'),
    path('approvals/<int:pk>/<str:action>/', views.approval_decide, name='approval_decide'),
    path('settings/', views.workflow_settings_view, name='settings'),
    path('announce/', views.announce, name='announce'),

    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:pk>/read/', views.notification_read, name='notification_read'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),

    path('calendar/', views.calendar_view, name='calendar'),
]
