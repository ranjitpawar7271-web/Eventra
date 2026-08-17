from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect

from events.models import Registration
from .forms import SignUpForm, ProfileUpdateForm


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def form_invalid(self, form):
        messages.error(self.request, "Invalid username or password. Please try again.")
        return super().form_invalid(form)


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to Eventra, {user.first_name}! Your account is ready.")
            return redirect('dashboard:dashboard')
        messages.error(request, "Please correct the errors below.")
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('pages:home')


@login_required
def profile_view(request):
    registrations = (
        Registration.objects.filter(user=request.user)
        .select_related('event')
        .order_by('-registered_at')[:5]
    )
    my_events_count = request.user.organized_events.count() if request.user.is_organizer else 0
    context = {
        'registrations': registrations,
        'my_events_count': my_events_count,
    }
    return render(request, 'profile/profile.html', context)


@login_required
def edit_profile_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('users:profile')
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, 'profile/edit_profile.html', {'form': form})


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password has been changed successfully.")
            return redirect('users:profile')
        messages.error(request, "Please correct the errors below.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'profile/change_password.html', {'form': form})
