from django.contrib import admin

from .models import MaintenanceSchedule, Venue, VenueBooking


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'capacity', 'is_active', 'created_by')
    list_filter = ('is_active', 'city')
    search_fields = ('name', 'city', 'address')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(VenueBooking)
class VenueBookingAdmin(admin.ModelAdmin):
    list_display = ('venue', 'event', 'booked_by', 'start_datetime', 'end_datetime', 'status')
    list_filter = ('status', 'venue')
    autocomplete_fields = ()


@admin.register(MaintenanceSchedule)
class MaintenanceScheduleAdmin(admin.ModelAdmin):
    list_display = ('venue', 'reason', 'start_datetime', 'end_datetime', 'created_by')
    list_filter = ('venue',)
