from django.contrib import admin

from .models import ApprovalStep, Notification, WorkflowSettings


@admin.register(WorkflowSettings)
class WorkflowSettingsAdmin(admin.ModelAdmin):
    list_display = ('require_event_approval', 'updated_by', 'updated_at')


@admin.register(ApprovalStep)
class ApprovalStepAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'stage', 'status', 'requested_by', 'requested_at', 'decided_by', 'decided_at')
    list_filter = ('stage', 'status')
    search_fields = ('comment',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('message', 'user__username')
