from django.contrib import admin

from .models import BackupLog


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'status', 'filename', 'performed_by', 'created_at')
    list_filter = ('action', 'status')
