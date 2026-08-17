from django.contrib import admin

from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'intent', 'created_at')
    list_filter = ('role', 'intent')
    search_fields = ('user__username', 'content')
    readonly_fields = ('user', 'role', 'content', 'intent', 'created_at')

    def has_add_permission(self, request):
        return False
