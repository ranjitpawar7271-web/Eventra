from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('event', 'sender', 'message_type', 'created_at')
    list_filter = ('message_type',)
    search_fields = ('event__title', 'sender__username', 'body')
