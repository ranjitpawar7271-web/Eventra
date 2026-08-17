from django.contrib import admin

from .models import DamageReport, Resource, ResourceAllocation


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'total_quantity', 'unit', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ResourceAllocation)
class ResourceAllocationAdmin(admin.ModelAdmin):
    list_display = ('resource', 'quantity', 'event', 'requested_by', 'start_datetime', 'end_datetime', 'status')
    list_filter = ('status', 'resource')


@admin.register(DamageReport)
class DamageReportAdmin(admin.ModelAdmin):
    list_display = ('resource', 'quantity_damaged', 'severity', 'status', 'reported_by', 'created_at')
    list_filter = ('status', 'severity', 'resource')
