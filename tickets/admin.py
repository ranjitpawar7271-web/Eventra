from django.contrib import admin

from .models import CheckInLog, Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_code', 'event', 'participant', 'ticket_type', 'status', 'issued_at')
    list_filter = ('ticket_type', 'status')
    search_fields = ('ticket_code', 'registration__event__title', 'registration__user__username', 'registration__user__email')
    readonly_fields = ('ticket_code', 'qr_token', 'issued_at')


@admin.register(CheckInLog)
class CheckInLogAdmin(admin.ModelAdmin):
    list_display = ('event', 'ticket', 'result', 'scanned_by', 'scanned_at')
    list_filter = ('result', 'event')
    search_fields = ('ticket__ticket_code', 'event__title')
