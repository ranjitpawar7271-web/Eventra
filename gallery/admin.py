from django.contrib import admin

from .models import Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ('event', 'uploaded_by', 'is_highlight', 'uploaded_at')
    list_filter = ('is_highlight',)
    search_fields = ('event__title', 'caption')
