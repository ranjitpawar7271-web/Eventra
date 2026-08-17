from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from users.models import User
from users.permissions import can_manage_catalog_item, role_required
from .forms import (
    AttendanceForm, AutoAssignForm, DepartmentForm, SalaryRecordForm,
    ShiftAssignmentForm, StaffOnboardForm, StaffProfileForm,
)
from .models import AttendanceRecord, Department, SalaryRecord, ShiftAssignment, StaffProfile

# NOTE on scope: `staff_onboard` (below) doesn't just create a StaffProfile
# — it also flips the target account's *platform-wide* `role` to
# User.STAFF (see StaffProfile's docstring). That's a global role grant,
# the same category of action as "Global role administration" that the
# spec explicitly keeps off-limits to Organizer (never give Organizer the
# power to mint privileged platform accounts for arbitrary users). So
# onboarding/department administration/salary records stay Super-Admin
# only. What Organizer gains here: editing the HR details of staff
# profiles they created, and full shift assignment (already granted below
# via SHIFT_MANAGER_ROLES), which is where "manage my event's staffing"
# actually lives day to day.
STAFF_ADMIN_ROLES = (User.SUPER_ADMIN,)
SHIFT_MANAGER_ROLES = (User.SUPER_ADMIN, User.ORGANIZER)


def _is_staff_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role in STAFF_ADMIN_ROLES)


def _can_manage_shifts(user):
    return user.is_authenticated and (user.is_superuser or user.role in SHIFT_MANAGER_ROLES)


@login_required
def staff_list(request):
    staff_members = StaffProfile.objects.filter(is_active=True).select_related('user', 'department')
    department_id = request.GET.get('department', '')
    if department_id.isdigit():
        staff_members = staff_members.filter(department_id=department_id)

    context = {
        'staff_members': staff_members,
        'departments': Department.objects.all(),
        'selected_department': department_id,
        'is_staff_admin': _is_staff_admin(request.user),
    }
    return render(request, 'staff/staff_list.html', context)


@login_required
def staff_detail(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    is_self = profile.user_id == request.user.id
    is_admin = _is_staff_admin(request.user)

    context = {
        'profile': profile,
        'is_self': is_self,
        'is_admin': is_admin,
        'can_view_salary': is_self or is_admin,
        'can_manage_shifts': _can_manage_shifts(request.user),
        'upcoming_shifts': profile.shifts.filter(status='assigned', end_datetime__gte=timezone.now())[:10],
        'attendance_records': profile.attendance_records.all()[:10],
        'salary_records': profile.salary_records.all()[:10] if (is_self or is_admin) else [],
    }
    return render(request, 'staff/staff_detail.html', context)


@role_required(*STAFF_ADMIN_ROLES)
def staff_onboard(request):
    if request.method == 'POST':
        form = StaffOnboardForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = form.cleaned_data['user']
            profile.created_by = request.user
            profile.save()
            # Promote the account to the Staff role, same sync pattern
            # Module 1 uses for is_organizer -> role.
            profile.user.role = User.STAFF
            profile.user.save(update_fields=['role'])
            messages.success(request, f"{profile.user.username} onboarded as staff.")
            return redirect('staff:staff_detail', pk=profile.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = StaffOnboardForm()
    return render(request, 'staff/staff_onboard_form.html', {'form': form})


@login_required
def staff_edit(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    # Super Admin: any profile. Organizer: only profiles they onboarded
    # (created_by) — editing HR details, not the underlying platform role.
    if not can_manage_catalog_item(request.user, profile, staff_unrestricted=False):
        messages.error(request, "You don't have permission to edit this staff profile.")
        return redirect('staff:staff_detail', pk=profile.pk)
    if request.method == 'POST':
        form = StaffProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Staff profile updated.")
            return redirect('staff:staff_detail', pk=profile.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = StaffProfileForm(instance=profile)
    return render(request, 'staff/staff_profile_form.html', {'form': form, 'profile': profile})


@role_required(*STAFF_ADMIN_ROLES)
def department_list(request):
    departments = Department.objects.all()
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Department added.")
            return redirect('staff:department_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = DepartmentForm()
    return render(request, 'staff/department_list.html', {'departments': departments, 'form': form})


@role_required(*STAFF_ADMIN_ROLES)
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        department.delete()
        messages.success(request, "Department removed.")
    return redirect('staff:department_list')


@role_required(*SHIFT_MANAGER_ROLES)
def shift_assign(request):
    if request.method == 'POST':
        form = ShiftAssignmentForm(request.POST, user=request.user)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.assigned_by = request.user
            shift.save()
            messages.success(request, f"{shift.staff} assigned to {shift.title}.")
            return redirect('staff:staff_detail', pk=shift.staff.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ShiftAssignmentForm(user=request.user)
    return render(request, 'staff/shift_assign_form.html', {'form': form})


@role_required(*SHIFT_MANAGER_ROLES)
def shift_auto_assign(request):
    result_staff = None
    searched = False
    if request.method == 'POST':
        form = AutoAssignForm(request.POST)
        if form.is_valid():
            searched = True
            department = form.cleaned_data['department']
            skill = form.cleaned_data['skill']
            start = form.cleaned_data['start_datetime']
            end = form.cleaned_data['end_datetime']
            candidates = StaffProfile.find_available(start, end, department=department, skill=skill)
            result_staff = candidates.first()
            if result_staff:
                shift = ShiftAssignment.objects.create(
                    staff=result_staff, title=form.cleaned_data['title'],
                    start_datetime=start, end_datetime=end,
                    assigned_by=request.user, auto_assigned=True,
                )
                messages.success(
                    request,
                    f"Auto-assigned {result_staff} ({result_staff.department or 'no dept'}) — "
                    f"no conflicting shifts found for that window."
                )
                return redirect('staff:staff_detail', pk=result_staff.pk)
            messages.warning(request, "No available staff matched those criteria for that time window.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AutoAssignForm()
    return render(request, 'staff/shift_auto_assign_form.html', {'form': form, 'searched': searched})


@login_required
def shift_update_status(request, pk, new_status):
    shift = get_object_or_404(ShiftAssignment, pk=pk)
    can_manage = _can_manage_shifts(request.user) or shift.staff.user_id == request.user.id
    if not can_manage:
        messages.error(request, "You don't have permission to update this shift.")
        return redirect('staff:staff_detail', pk=shift.staff.pk)
    if new_status not in ('completed', 'cancelled'):
        messages.error(request, "Invalid status.")
        return redirect('staff:staff_detail', pk=shift.staff.pk)
    if request.method == 'POST':
        shift.status = new_status
        shift.save()
        messages.success(request, f"Shift marked {new_status}.")
    return redirect('staff:staff_detail', pk=shift.staff.pk)


@login_required
def attendance_mark(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    is_self = profile.user_id == request.user.id
    if not (is_self or _is_staff_admin(request.user)):
        messages.error(request, "You can only record your own attendance.")
        return redirect('staff:staff_detail', pk=profile.pk)

    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            record, created = AttendanceRecord.objects.update_or_create(
                staff=profile, date=form.cleaned_data['date'],
                defaults={
                    'status': form.cleaned_data['status'],
                    'check_in': form.cleaned_data['check_in'],
                    'check_out': form.cleaned_data['check_out'],
                    'notes': form.cleaned_data['notes'],
                    'recorded_by': request.user,
                },
            )
            messages.success(request, "Attendance recorded.")
            return redirect('staff:staff_detail', pk=profile.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = AttendanceForm(initial={'date': timezone.now().date(), 'check_in': timezone.now()})
    return render(request, 'staff/attendance_form.html', {'form': form, 'profile': profile})


@role_required(*STAFF_ADMIN_ROLES)
def salary_record_create(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    if request.method == 'POST':
        form = SalaryRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.staff = profile
            record.recorded_by = request.user
            record.save()
            messages.success(request, "Salary record added.")
            return redirect('staff:staff_detail', pk=profile.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = SalaryRecordForm()
    return render(request, 'staff/salary_record_form.html', {'form': form, 'profile': profile})
