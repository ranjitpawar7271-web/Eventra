from django.urls import path

from . import views

app_name = 'wishlist'

urlpatterns = [
    path('', views.wishlist_list, name='wishlist_list'),
    path('toggle/<slug:slug>/', views.toggle_favorite, name='toggle_favorite'),
]
