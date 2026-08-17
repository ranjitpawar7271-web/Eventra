from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user', 'event', 'amount', 'payment_method', 'status', 'refund_status', 'created_at')
    list_filter = ('status', 'payment_method', 'refund_status')
    search_fields = ('transaction_id', 'user__username', 'user__email', 'event__title')
    readonly_fields = ('transaction_id', 'created_at', 'updated_at')
