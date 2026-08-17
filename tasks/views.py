from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from events.models import Event
from users.models import User
from .forms import TaskCommentForm, TaskForm
from .models import Task


def _can_manage_board(user, event):
    """Full control over the board: create/edit/delete any card, assign
    anyone. Same organizer-owns-their-event-or-staff/admin shape used by
    budget and sponsors."""
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


def _can_view_board(user, event):
    """Managers, plus anyone currently assigned at least one card on this
    board — a volunteer or vendor contact shouldn't see every event's
    internal task board, only ones they're actually working on."""
    if _can_manage_board(user, event):
        return True
    return user.is_authenticated and Task.objects.filter(event=event, assigned_to=user).exists()


def _can_touch_task(user, task):
    """Move status / comment: a manager, or the person the card is
    assigned to."""
    return _can_manage_board(user, task.event) or (
        user.is_authenticated and task.assigned_to_id == user.id
    )


@login_required
def task_board(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_view_board(request.user, event):
        messages.error(request, "You don't have access to this event's task board.")
        return redirect('events:event_detail', slug=event.slug)

    tasks = event.tasks.select_related('assigned_to').all()
    columns = [
        {'code': code, 'label': label, 'tasks': [t for t in tasks if t.status == code]}
        for code, label in Task.STATUS_CHOICES
    ]

    context = {
        'event': event,
        'columns': columns,
        'can_manage': _can_manage_board(request.user, event),
    }
    return render(request, 'tasks/task_board.html', context)


@login_required
def task_create(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_manage_board(request.user, event):
        messages.error(request, "You don't have permission to add tasks to this event.")
        return redirect('events:event_detail', slug=event.slug)

    if request.method == 'POST':
        form = TaskForm(request.POST, event=event)
        if form.is_valid():
            task = form.save(commit=False)
            task.event = event
            task.created_by = request.user
            task.save()
            messages.success(request, f"Task '{task.title}' added.")
            return redirect('tasks:task_board', event_slug=event.slug)
    else:
        form = TaskForm(event=event)

    return render(request, 'tasks/task_form.html', {'form': form, 'event': event, 'is_edit': False})


@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_manage_board(request.user, task.event):
        messages.error(request, "You don't have permission to edit this task.")
        return redirect('tasks:task_detail', pk=task.pk)

    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, event=task.event)
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated.")
            return redirect('tasks:task_detail', pk=task.pk)
    else:
        form = TaskForm(instance=task, event=task.event)

    return render(request, 'tasks/task_form.html', {'form': form, 'event': task.event, 'is_edit': True, 'task': task})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_view_board(request.user, task.event):
        messages.error(request, "You don't have access to this task.")
        return redirect('events:event_detail', slug=task.event.slug)

    comment_form = TaskCommentForm()
    context = {
        'task': task,
        'comments': task.comments.select_related('author').all(),
        'comment_form': comment_form,
        'can_manage': _can_manage_board(request.user, task.event),
        'can_touch': _can_touch_task(request.user, task),
    }
    return render(request, 'tasks/task_detail.html', context)


@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_manage_board(request.user, task.event):
        messages.error(request, "You don't have permission to delete this task.")
        return redirect('tasks:task_detail', pk=task.pk)

    if request.method == 'POST':
        event_slug = task.event.slug
        task.delete()
        messages.success(request, "Task deleted.")
        return redirect('tasks:task_board', event_slug=event_slug)
    return render(request, 'tasks/task_confirm_delete.html', {'task': task})


@login_required
@require_POST
def task_status_update(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_touch_task(request.user, task):
        messages.error(request, "You don't have permission to move this task.")
        return redirect('tasks:task_board', event_slug=task.event.slug)

    new_status = request.POST.get('status')
    if new_status in dict(Task.STATUS_CHOICES):
        task.status = new_status
        task.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"'{task.title}' moved to {task.get_status_display()}.")

    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('tasks:task_board', event_slug=task.event.slug)


@login_required
@require_POST
def task_comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not _can_touch_task(request.user, task):
        messages.error(request, "You don't have permission to comment on this task.")
        return redirect('tasks:task_detail', pk=task.pk)

    form = TaskCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
    return redirect('tasks:task_detail', pk=task.pk)


@login_required
def my_tasks(request):
    tasks = Task.objects.filter(assigned_to=request.user).select_related('event')
    return render(request, 'tasks/my_tasks.html', {'tasks': tasks})
