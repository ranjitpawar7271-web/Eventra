from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from users.models import User
from users.permissions import can_manage_catalog_item, role_required
from .forms import CategoryForm
from .models import Category

# Category is a shared, platform-wide catalog (not scoped to a single
# organization/event — see categories/models.py). Super Admin and Staff
# keep full access as before; Organizer may now create categories and
# manage the ones they created (see can_manage_catalog_item).
CATEGORY_MANAGER_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)


def category_list(request):
    categories = Category.objects.annotate(event_count=Count('events')).order_by('name')
    context = {
        'categories': categories,
        'can_create': request.user.is_authenticated and request.user.role in CATEGORY_MANAGER_ROLES,
    }
    return render(request, 'categories/category_list.html', context)


@role_required(*CATEGORY_MANAGER_ROLES)
def category_create(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            messages.success(request, "Category created successfully.")
            return redirect('categories:category_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = CategoryForm()
    return render(request, 'categories/category_form.html', {'form': form, 'title': 'Add Category'})


@login_required
def category_update(request, slug):
    category = get_object_or_404(Category, slug=slug)
    if not can_manage_catalog_item(request.user, category):
        messages.error(request, "You don't have permission to edit this category.")
        return redirect('categories:category_list')

    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated successfully.")
            return redirect('categories:category_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = CategoryForm(instance=category)
    return render(request, 'categories/category_form.html', {'form': form, 'title': 'Edit Category'})


@login_required
def category_delete(request, slug):
    category = get_object_or_404(Category, slug=slug)
    if not can_manage_catalog_item(request.user, category):
        messages.error(request, "You don't have permission to delete this category.")
        return redirect('categories:category_list')

    if request.method == 'POST':
        category.delete()
        messages.success(request, "Category deleted successfully.")
        return redirect('categories:category_list')
    return render(request, 'categories/category_confirm_delete.html', {'category': category})
