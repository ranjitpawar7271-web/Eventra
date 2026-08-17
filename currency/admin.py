from django.contrib import admin

from .models import Currency


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'symbol', 'rate_to_base', 'is_base', 'updated_at')
    list_filter = ('is_base',)
    search_fields = ('code', 'name')
