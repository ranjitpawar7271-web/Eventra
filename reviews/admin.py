from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'rating', 'venue_rating', 'organization_rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('event__title', 'user__username', 'comment')
