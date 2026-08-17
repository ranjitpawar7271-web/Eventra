from django.contrib import admin

from .models import EventSponsorship, Sponsor


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('company_name', 'contact_person', 'email')
    prepopulated_fields = {'slug': ('company_name',)}


@admin.register(EventSponsorship)
class EventSponsorshipAdmin(admin.ModelAdmin):
    list_display = ('sponsor', 'event', 'package', 'amount', 'status', 'created_at')
    list_filter = ('package', 'status')
    search_fields = ('sponsor__company_name', 'event__title')
