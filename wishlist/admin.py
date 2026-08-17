from django.contrib import admin

from .models import FavoriteEvent


@admin.register(FavoriteEvent)
class FavoriteEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'created_at')
    search_fields = ('user__username', 'event__title')
