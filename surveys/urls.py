from django.urls import path

from . import views

app_name = 'surveys'

urlpatterns = [
    path('events/<slug:event_slug>/', views.survey_list, name='survey_list'),
    path('events/<slug:event_slug>/add/', views.survey_create, name='survey_create'),
    path('<int:pk>/manage/', views.survey_manage, name='survey_manage'),
    path('<int:pk>/toggle-open/', views.survey_toggle_open, name='survey_toggle_open'),
    path('<int:pk>/delete/', views.survey_delete, name='survey_delete'),
    path('<int:pk>/respond/', views.survey_respond, name='survey_respond'),
    path('<int:pk>/results/', views.survey_results, name='survey_results'),
    path('questions/<int:pk>/delete/', views.question_delete, name='question_delete'),
]
