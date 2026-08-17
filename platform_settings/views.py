from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import PlatformSettingsForm
from .models import PlatformSettings


@login_required
def settings_edit(request):
    if not request.user.is_super_admin:
        messages.error(request, "Platform settings are restricted to Super Admins.")
        return redirect('dashboard:dashboard')

    settings_obj = PlatformSettings.load()
    if request.method == 'POST':
        form = PlatformSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, "Platform settings updated.")
            return redirect('platform_settings:settings_edit')
    else:
        form = PlatformSettingsForm(instance=settings_obj)
    return render(request, 'platform_settings/settings_edit.html', {'form': form, 'settings_obj': settings_obj})
