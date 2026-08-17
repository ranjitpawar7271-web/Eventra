from django.contrib import admin

from .models import Event, Registration, WaitlistEntry


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'organizer', 'start_date', 'status', 'capacity')
    list_filter = ('status', 'category')
    search_fields = ('title', 'location')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'status', 'registered_at')
    list_filter = ('status',)


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'position', 'status', 'joined_at', 'invitation_expires_at')
    list_filter = ('status',)
    search_fields = ('event__title', 'user__username', 'user__email')
