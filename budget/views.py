from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from events.models import Event
from users.models import User
from users.permissions import role_required
from .forms import EventBudgetForm, ExpenseForm, ExpenseStatusForm, RevenueEntryForm
from .models import EventBudget, Expense, RevenueEntry

# Per spec: Organizer (for their own events) and Super Admin/Staff record
# expenses/revenue and view budget vs. actual. No separate approver role
# is introduced — the same set of people who can log a line item can also
# move its status along, same as Module 4's contract-status pattern.
BUDGET_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)
BUDGET_ADMIN_ROLES = (User.SUPER_ADMIN, User.STAFF)


def _can_manage_budget(user, event):
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    return user.role == User.ORGANIZER and event.organizer_id == user.id


@role_required(*BUDGET_ROLES)
def budget_list(request):
    is_admin = request.user.is_super_admin or request.user.is_staff_role

    budgets = EventBudget.objects.select_related('event', 'event__organizer')
    events_without_budget = Event.objects.filter(budget__isnull=True)
    if not is_admin:
        budgets = budgets.filter(event__organizer=request.user)
        events_without_budget = events_without_budget.filter(organizer=request.user)

    context = {
        'budgets': budgets,
        # Events this user manages that don't have a budget yet, so
        # they have a clear way to set one up instead of hunting for it.
        'events_without_budget': events_without_budget,
    }
    return render(request, 'budget/budget_list.html', context)


@login_required
def budget_detail(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    can_manage = _can_manage_budget(request.user, event)
    if not can_manage:
        messages.error(request, "You don't have permission to view this event's budget.")
        return redirect('events:event_detail', slug=event.slug)

    budget = EventBudget.objects.filter(event=event).first()
    context = {
        'event': event,
        'budget': budget,
        'can_manage': can_manage,
    }
    if budget:
        context.update({
            'expenses': budget.expenses.all(),
            'revenue_entries': budget.revenue_entries.all(),
            'category_breakdown': budget.category_breakdown,
            'expense_form': ExpenseForm(initial={'status': 'pending'}),
            'revenue_form': RevenueEntryForm(),
        })
    return render(request, 'budget/budget_detail.html', context)


@login_required
def budget_setup(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if not _can_manage_budget(request.user, event):
        messages.error(request, "You don't have permission to set up this event's budget.")
        return redirect('events:event_detail', slug=event.slug)

    budget = EventBudget.objects.filter(event=event).first()
    if request.method == 'POST':
        form = EventBudgetForm(request.POST, instance=budget)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.event = event
            if not budget.pk:
                budget.created_by = request.user
            budget.save()
            messages.success(request, "Budget saved.")
            return redirect('budget:budget_detail', event_slug=event.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = EventBudgetForm(instance=budget)
    return render(request, 'budget/budget_form.html', {'form': form, 'event': event, 'budget': budget})


@login_required
def expense_create(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    budget = get_object_or_404(EventBudget, event=event)
    if not _can_manage_budget(request.user, event):
        messages.error(request, "You don't have permission to log expenses for this event.")
        return redirect('budget:budget_detail', event_slug=event.slug)

    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.budget = budget
            expense.recorded_by = request.user
            expense.save()
            messages.success(request, "Expense logged.")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect('budget:budget_detail', event_slug=event.slug)


@login_required
def expense_status_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    event = expense.budget.event
    if not _can_manage_budget(request.user, event):
        messages.error(request, "You don't have permission to update this expense.")
        return redirect('budget:budget_detail', event_slug=event.slug)

    if request.method == 'POST':
        form = ExpenseStatusForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense status updated.")
    return redirect('budget:budget_detail', event_slug=event.slug)


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    event = expense.budget.event
    if not _can_manage_budget(request.user, event):
        messages.error(request, "You don't have permission to remove this expense.")
        return redirect('budget:budget_detail', event_slug=event.slug)

    if request.method == 'POST':
        expense.delete()
        messages.success(request, "Expense removed.")
    return redirect('budget:budget_detail', event_slug=event.slug)


@login_required
def revenue_create(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    budget = get_object_or_404(EventBudget, event=event)
    if not _can_manage_budget(request.user, event):
        messages.error(request, "You don't have permission to log revenue for this event.")
        return redirect('budget:budget_detail', event_slug=event.slug)

    if request.method == 'POST':
        form = RevenueEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.budget = budget
            entry.recorded_by = request.user
            entry.save()
            messages.success(request, "Revenue recorded.")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect('budget:budget_detail', event_slug=event.slug)


@login_required
def revenue_delete(request, pk):
    entry = get_object_or_404(RevenueEntry, pk=pk)
    event = entry.budget.event
    if not _can_manage_budget(request.user, event):
        messages.error(request, "You don't have permission to remove this entry.")
        return redirect('budget:budget_detail', event_slug=event.slug)

    if request.method == 'POST':
        entry.delete()
        messages.success(request, "Revenue entry removed.")
    return redirect('budget:budget_detail', event_slug=event.slug)
