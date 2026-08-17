from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.staff_list, name='staff_list'),
    path('onboard/', views.staff_onboard, name='staff_onboard'),
    path('departments/', views.department_list, name='department_list'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),
    path('shifts/assign/', views.shift_assign, name='shift_assign'),
    path('shifts/auto-assign/', views.shift_auto_assign, name='shift_auto_assign'),
    path('shifts/<int:pk>/complete/', views.shift_update_status, {'new_status': 'completed'}, name='shift_complete'),
    path('shifts/<int:pk>/cancel/', views.shift_update_status, {'new_status': 'cancelled'}, name='shift_cancel'),
    path('<int:pk>/', views.staff_detail, name='staff_detail'),
    path('<int:pk>/edit/', views.staff_edit, name='staff_edit'),
    path('<int:pk>/attendance/mark/', views.attendance_mark, name='attendance_mark'),
    path('<int:pk>/salary/add/', views.salary_record_create, name='salary_record_create'),
]
