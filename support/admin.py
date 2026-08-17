from django.contrib import admin

from .models import FAQItem, PlatformAnnouncement, SupportRequest


@admin.register(FAQItem)
class FAQItemAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'is_published', 'order')
    list_filter = ('category', 'is_published')
    search_fields = ('question', 'answer')


@admin.register(PlatformAnnouncement)
class PlatformAnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'body')


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ('subject', 'request_type', 'status', 'email', 'created_at')
    list_filter = ('request_type', 'status')
    search_fields = ('subject', 'message', 'email', 'name')
