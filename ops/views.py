from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .backup_utils import RestoreValidationError, create_backup_json, execute_restore
from .health import get_system_health
from .models import BackupLog

# Per the module plan's own permission note: "sponsor management and
# system health restricted to Super Admin." Backup/Restore carries the
# same or greater risk, so it gets the same, stricter bar — Staff is not
# enough here, unlike most other admin-ish panels in this project.


def _is_super_admin(user):
    return user.is_authenticated and user.is_super_admin


@login_required
def system_health(request):
    if not _is_super_admin(request.user):
        messages.error(request, "System health is restricted to Super Admins.")
        return redirect('dashboard:dashboard')

    context = get_system_health()
    context['recent_backups'] = BackupLog.objects.select_related('performed_by')[:10]
    return render(request, 'ops/system_health.html', context)


@login_required
@require_POST
def backup_create(request):
    if not _is_super_admin(request.user):
        messages.error(request, "Backups are restricted to Super Admins.")
        return redirect('dashboard:dashboard')

    content, object_count = create_backup_json()
    filename = f"eventra-backup-{timezone.now().strftime('%Y%m%d-%H%M%S')}.json"
    BackupLog.objects.create(
        action=BackupLog.ACTION_BACKUP, status=BackupLog.STATUS_SUCCESS,
        filename=filename, details=f"{object_count} objects", performed_by=request.user,
    )
    response = HttpResponse(content, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def restore_upload(request):
    if not _is_super_admin(request.user):
        messages.error(request, "Restore is restricted to Super Admins.")
        return redirect('dashboard:dashboard')

    if request.method == 'POST':
        uploaded = request.FILES.get('backup_file')
        confirmed = request.POST.get('confirm') == 'yes'

        if not uploaded:
            messages.error(request, "Choose a backup file to restore.")
            return redirect('ops:restore_upload')
        if not confirmed:
            messages.error(request, "You must check the confirmation box to proceed — restoring overwrites existing data.")
            return redirect('ops:restore_upload')

        try:
            content = uploaded.read().decode('utf-8')
        except UnicodeDecodeError:
            messages.error(request, "That file doesn't look like a valid text/JSON backup.")
            return redirect('ops:restore_upload')

        try:
            object_count = execute_restore(content)
        except RestoreValidationError as exc:
            BackupLog.objects.create(
                action=BackupLog.ACTION_RESTORE, status=BackupLog.STATUS_FAILED,
                filename=uploaded.name, details=str(exc), performed_by=request.user,
            )
            messages.error(request, f"Restore failed: {exc}")
            return redirect('ops:restore_upload')
        except Exception as exc:
            BackupLog.objects.create(
                action=BackupLog.ACTION_RESTORE, status=BackupLog.STATUS_FAILED,
                filename=uploaded.name, details=str(exc), performed_by=request.user,
            )
            messages.error(request, f"Restore failed and was rolled back: {exc}")
            return redirect('ops:restore_upload')

        BackupLog.objects.create(
            action=BackupLog.ACTION_RESTORE, status=BackupLog.STATUS_SUCCESS,
            filename=uploaded.name, details=f"{object_count} objects", performed_by=request.user,
        )
        messages.success(request, f"Restore complete — {object_count} objects loaded.")
        return redirect('ops:system_health')

    return render(request, 'ops/restore_upload.html')
