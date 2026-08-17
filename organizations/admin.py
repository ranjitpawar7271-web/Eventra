from django.contrib import admin

from .models import Organization, OrganizationMembership


class MembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'member_count', 'event_count', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    inlines = [MembershipInline]
