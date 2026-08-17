from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('my-payments/', views.my_payments, name='my_payments'),
    path('<int:payment_id>/checkout/', views.checkout, name='checkout'),
    path('<int:payment_id>/process/', views.process_payment, name='process_payment'),
    path('<int:payment_id>/refund/', views.refund, name='refund'),
    path('events/<slug:slug>/', views.event_payments, name='event_payments'),
]
