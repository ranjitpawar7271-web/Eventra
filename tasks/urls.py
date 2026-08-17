from django.urls import path

from . import views

app_name = 'tasks'

urlpatterns = [
    path('my-tasks/', views.my_tasks, name='my_tasks'),
    path('<int:pk>/', views.task_detail, name='task_detail'),
    path('<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('<int:pk>/status/', views.task_status_update, name='task_status_update'),
    path('<int:pk>/comment/', views.task_comment_create, name='task_comment_create'),
    path('events/<slug:event_slug>/board/', views.task_board, name='task_board'),
    path('events/<slug:event_slug>/add/', views.task_create, name='task_create'),
]
