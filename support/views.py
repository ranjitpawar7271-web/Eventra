from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from users.models import User
from .forms import FAQItemForm, PlatformAnnouncementForm, SupportRequestForm, SupportRequestStatusForm
from .models import FAQItem, PlatformAnnouncement, SupportRequest


def _can_manage_content(user):
    """FAQ items and platform announcements are site-wide, so this is a
    platform-level permission (Staff/Super Admin), not the usual
    organizer-owns-their-event check used everywhere else in this
    project — there's no "owner" for a platform-wide FAQ entry."""
    return user.is_authenticated and (user.is_super_admin or user.is_staff_role)


# --- FAQ / Help Center -----------------------------------------------

def faq_list(request):
    """Public."""
    items = FAQItem.objects.all()
    can_manage = request.user.is_authenticated and _can_manage_content(request.user)
    if not can_manage:
        items = items.filter(is_published=True)
    return render(request, 'support/faq_list.html', {'items': items, 'can_manage': can_manage})


@login_required
def faq_create(request):
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to manage the FAQ.")
        return redirect('support:faq_list')
    if request.method == 'POST':
        form = FAQItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.save()
            messages.success(request, "FAQ item added.")
            return redirect('support:faq_list')
    else:
        form = FAQItemForm()
    return render(request, 'support/faq_form.html', {'form': form, 'is_edit': False})


@login_required
def faq_edit(request, pk):
    item = get_object_or_404(FAQItem, pk=pk)
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to manage the FAQ.")
        return redirect('support:faq_list')
    if request.method == 'POST':
        form = FAQItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "FAQ item updated.")
            return redirect('support:faq_list')
    else:
        form = FAQItemForm(instance=item)
    return render(request, 'support/faq_form.html', {'form': form, 'is_edit': True, 'item': item})


@login_required
def faq_delete(request, pk):
    item = get_object_or_404(FAQItem, pk=pk)
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to manage the FAQ.")
        return redirect('support:faq_list')
    if request.method == 'POST':
        item.delete()
        messages.success(request, "FAQ item removed.")
        return redirect('support:faq_list')
    return render(request, 'support/faq_confirm_delete.html', {'item': item})


# --- Announcement Board ------------------------------------------------

def announcement_list(request):
    """Public."""
    announcements = PlatformAnnouncement.objects.all()
    can_manage = request.user.is_authenticated and _can_manage_content(request.user)
    if not can_manage:
        announcements = announcements.filter(is_active=True)
    return render(request, 'support/announcement_list.html', {
        'announcements': announcements, 'can_manage': can_manage,
    })


@login_required
def announcement_create(request):
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to post announcements.")
        return redirect('support:announcement_list')
    if request.method == 'POST':
        form = PlatformAnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.created_by = request.user
            announcement.save()
            messages.success(request, "Announcement posted.")
            return redirect('support:announcement_list')
    else:
        form = PlatformAnnouncementForm()
    return render(request, 'support/announcement_form.html', {'form': form, 'is_edit': False})


@login_required
def announcement_edit(request, pk):
    announcement = get_object_or_404(PlatformAnnouncement, pk=pk)
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to manage announcements.")
        return redirect('support:announcement_list')
    if request.method == 'POST':
        form = PlatformAnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, "Announcement updated.")
            return redirect('support:announcement_list')
    else:
        form = PlatformAnnouncementForm(instance=announcement)
    return render(request, 'support/announcement_form.html', {'form': form, 'is_edit': True, 'announcement': announcement})


@login_required
def announcement_delete(request, pk):
    announcement = get_object_or_404(PlatformAnnouncement, pk=pk)
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to manage announcements.")
        return redirect('support:announcement_list')
    if request.method == 'POST':
        announcement.delete()
        messages.success(request, "Announcement removed.")
        return redirect('support:announcement_list')
    return render(request, 'support/announcement_confirm_delete.html', {'announcement': announcement})


# --- Contact Support / Feedback ----------------------------------------

def support_contact(request):
    """Public — works for anonymous visitors, same as any ordinary
    contact form. If the person is logged in, their name/email are
    pre-filled and the submission is linked to their account so it shows
    up in `my_support_requests`."""
    initial = {}
    if request.user.is_authenticated:
        initial = {'name': request.user.get_full_name() or request.user.username, 'email': request.user.email}

    if request.method == 'POST':
        form = SupportRequestForm(request.POST)
        if form.is_valid():
            support_request = form.save(commit=False)
            if request.user.is_authenticated:
                support_request.user = request.user
            support_request.save()
            messages.success(request, "Thanks — we've received your message and will follow up soon.")
            return redirect('support:support_contact')
    else:
        form = SupportRequestForm(initial=initial)

    return render(request, 'support/support_contact.html', {'form': form})


@login_required
def my_support_requests(request):
    requests_qs = SupportRequest.objects.filter(user=request.user)
    return render(request, 'support/my_support_requests.html', {'requests': requests_qs})


@login_required
def support_inbox(request):
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to view the support inbox.")
        return redirect('dashboard:dashboard')

    requests_qs = SupportRequest.objects.select_related('user', 'resolved_by')
    status_filter = request.GET.get('status', '')
    if status_filter in dict(SupportRequest.STATUS_CHOICES):
        requests_qs = requests_qs.filter(status=status_filter)

    return render(request, 'support/support_inbox.html', {
        'requests': requests_qs,
        'status_filter': status_filter,
        'status_choices': SupportRequest.STATUS_CHOICES,
    })


@login_required
def support_request_status_update(request, pk):
    support_request = get_object_or_404(SupportRequest, pk=pk)
    if not _can_manage_content(request.user):
        messages.error(request, "You don't have permission to update this request.")
        return redirect('support:support_inbox')
    if request.method == 'POST':
        form = SupportRequestStatusForm(request.POST, instance=support_request)
        if form.is_valid():
            support_request = form.save(commit=False)
            if support_request.status == SupportRequest.STATUS_RESOLVED and not support_request.resolved_by:
                support_request.resolved_by = request.user
            support_request.save()
            messages.success(request, "Status updated.")
    return redirect('support:support_inbox')
