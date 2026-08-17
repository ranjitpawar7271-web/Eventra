from django.contrib import admin

from .models import Task, TaskComment


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'status', 'priority', 'assigned_to', 'due_date')
    list_filter = ('status', 'priority')
    search_fields = ('title', 'event__title')
    inlines = [TaskCommentInline]
