from django.contrib import admin

from .models import AttendanceRecord, Department, SalaryRecord, ShiftAssignment, StaffProfile


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'department', 'designation', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('employee_id', 'user__username')


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ('staff', 'title', 'event', 'start_datetime', 'end_datetime', 'status', 'auto_assigned')
    list_filter = ('status', 'auto_assigned')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('staff', 'date', 'status', 'check_in', 'check_out')
    list_filter = ('status',)


@admin.register(SalaryRecord)
class SalaryRecordAdmin(admin.ModelAdmin):
    list_display = ('staff', 'period_start', 'period_end', 'basic_amount', 'net_amount', 'status')
    list_filter = ('status',)
