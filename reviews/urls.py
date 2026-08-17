from django.urls import path

from . import views

app_name = 'reviews'

urlpatterns = [
    path('events/<slug:slug>/', views.event_reviews, name='event_reviews'),
    path('events/<slug:slug>/write/', views.review_create, name='review_create'),
    path('<int:pk>/edit/', views.review_edit, name='review_edit'),
    path('<int:pk>/delete/', views.review_delete, name='review_delete'),
]
