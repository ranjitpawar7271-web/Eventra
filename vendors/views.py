from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from users.models import User
from users.permissions import role_required
from .forms import (
    VendorContractForm, VendorContractStatusForm, VendorDocumentForm, VendorPaymentForm,
    VendorProfileForm, VendorRatingForm, VendorServiceForm,
)
from .models import VendorContract, VendorDocument, VendorPayment, VendorProfile, VendorRating, VendorService

# Vendor *directory* trust decisions (approve/reject/suspend a vendor's
# public listing) stay Super Admin/Staff only — same reasoning as staff
# onboarding: it's a platform-wide vetting decision, not something scoped
# to "my organization/events". Hiring/managing a vendor *for your own
# event* (contracts, services, documents, ratings, payments) is where
# Organizer gets full access below, scoped by event ownership.
VENDOR_MANAGER_ROLES = (User.SUPER_ADMIN, User.STAFF)
CONTRACT_ROLES = (User.SUPER_ADMIN, User.STAFF, User.ORGANIZER)


def _can_manage_vendors(user):
    return user.is_authenticated and (user.is_superuser or user.role in VENDOR_MANAGER_ROLES)


def _can_manage_contracts(user):
    return user.is_authenticated and (user.is_superuser or user.role in CONTRACT_ROLES)


def _owns_vendor(user, vendor):
    return user.is_authenticated and vendor.user_id == user.id


def _can_manage_contract(user, contract):
    """Object-level check for a specific VendorContract: Super Admin/Staff
    always; Organizer only if they created the contract or organize its
    linked event (contracts can be created without an event attached, so
    `created_by` is the fallback ownership signal)."""
    if not user.is_authenticated:
        return False
    if user.is_super_admin or user.is_staff_role:
        return True
    if user.role != User.ORGANIZER:
        return False
    if contract.event_id and contract.event.organizer_id == user.id:
        return True
    return contract.created_by_id == user.id


def vendor_list(request):
    vendors = VendorProfile.objects.all()
    can_manage = _can_manage_vendors(request.user)
    if not can_manage:
        vendors = vendors.filter(status='approved')

    query = request.GET.get('q', '').strip()
    service_type = request.GET.get('service_type', '')
    if query:
        vendors = vendors.filter(Q(company_name__icontains=query) | Q(description__icontains=query))
    if service_type:
        vendors = vendors.filter(service_type=service_type)

    paginator = Paginator(vendors, 9)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'query': query,
        'selected_service_type': service_type,
        'service_types': VendorProfile.SERVICE_TYPE_CHOICES,
        'can_manage_vendors': can_manage,
    }
    return render(request, 'vendors/vendor_list.html', context)


def vendor_detail(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    can_manage = _can_manage_vendors(request.user)
    is_owner = _owns_vendor(request.user, vendor)

    if vendor.status != 'approved' and not (can_manage or is_owner):
        messages.error(request, "This vendor profile isn't public yet.")
        return redirect('vendors:vendor_list')

    context = {
        'vendor': vendor,
        'services': vendor.services.filter(is_active=True),
        'ratings': vendor.ratings.select_related('rated_by', 'event')[:10],
        'contracts': vendor.contracts.all()[:10] if (can_manage or is_owner) else [],
        'documents': vendor.documents.all() if (can_manage or is_owner) else [],
        'can_manage': can_manage,
        'is_owner': is_owner,
        'can_create_contract': _can_manage_contracts(request.user),
    }
    return render(request, 'vendors/vendor_detail.html', context)


@login_required
def vendor_profile_create(request):
    if hasattr(request.user, 'vendor_profile'):
        return redirect('vendors:vendor_profile_edit')

    if request.user.role != User.VENDOR and not request.user.is_superuser:
        messages.error(request, "Only accounts registered with the Vendor role can create a vendor profile.")
        return redirect('dashboard:dashboard')

    if request.method == 'POST':
        form = VendorProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, "Vendor profile submitted — it will appear publicly once approved.")
            return redirect('vendors:vendor_detail', slug=profile.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VendorProfileForm()
    return render(request, 'vendors/vendor_profile_form.html', {'form': form, 'title': 'Register as a Vendor'})


@login_required
def vendor_profile_edit(request):
    vendor = get_object_or_404(VendorProfile, user=request.user)
    if request.method == 'POST':
        form = VendorProfileForm(request.POST, request.FILES, instance=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, "Vendor profile updated.")
            return redirect('vendors:vendor_detail', slug=vendor.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VendorProfileForm(instance=vendor)
    return render(request, 'vendors/vendor_profile_form.html', {'form': form, 'title': 'Edit Vendor Profile', 'vendor': vendor})


@role_required(*VENDOR_MANAGER_ROLES)
def vendor_approve(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if request.method == 'POST':
        vendor.status = 'approved'
        vendor.reviewed_by = request.user
        vendor.save()
        messages.success(request, f"{vendor.company_name} approved and now listed publicly.")
    return redirect('vendors:vendor_detail', slug=vendor.slug)


@role_required(*VENDOR_MANAGER_ROLES)
def vendor_reject(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if request.method == 'POST':
        vendor.status = 'rejected'
        vendor.reviewed_by = request.user
        vendor.save()
        messages.success(request, f"{vendor.company_name} rejected.")
    return redirect('vendors:vendor_detail', slug=vendor.slug)


@role_required(*VENDOR_MANAGER_ROLES)
def vendor_suspend(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if request.method == 'POST':
        vendor.status = 'suspended'
        vendor.reviewed_by = request.user
        vendor.save()
        messages.success(request, f"{vendor.company_name} suspended.")
    return redirect('vendors:vendor_detail', slug=vendor.slug)


def _require_owner_or_manager(request, vendor):
    if not (_owns_vendor(request.user, vendor) or _can_manage_vendors(request.user)):
        messages.error(request, "You don't have permission to manage this vendor's listings.")
        return False
    return True


@login_required
def vendor_service_create(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if not _require_owner_or_manager(request, vendor):
        return redirect('vendors:vendor_detail', slug=vendor.slug)

    if request.method == 'POST':
        form = VendorServiceForm(request.POST)
        if form.is_valid():
            service = form.save(commit=False)
            service.vendor = vendor
            service.save()
            messages.success(request, "Service added.")
            return redirect('vendors:vendor_detail', slug=vendor.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VendorServiceForm()
    return render(request, 'vendors/vendor_service_form.html', {'form': form, 'vendor': vendor})


@login_required
def vendor_service_delete(request, pk):
    service = get_object_or_404(VendorService, pk=pk)
    vendor = service.vendor
    if not _require_owner_or_manager(request, vendor):
        return redirect('vendors:vendor_detail', slug=vendor.slug)
    if request.method == 'POST':
        service.delete()
        messages.success(request, "Service removed.")
    return redirect('vendors:vendor_detail', slug=vendor.slug)


@login_required
def vendor_document_upload(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if not _require_owner_or_manager(request, vendor):
        return redirect('vendors:vendor_detail', slug=vendor.slug)

    if request.method == 'POST':
        form = VendorDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.vendor = vendor
            document.uploaded_by = request.user
            document.save()
            messages.success(request, "Document uploaded.")
            return redirect('vendors:vendor_detail', slug=vendor.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VendorDocumentForm()
    return render(request, 'vendors/vendor_document_form.html', {'form': form, 'vendor': vendor})


@login_required
def vendor_document_delete(request, pk):
    document = get_object_or_404(VendorDocument, pk=pk)
    vendor = document.vendor
    if not _require_owner_or_manager(request, vendor):
        return redirect('vendors:vendor_detail', slug=vendor.slug)
    if request.method == 'POST':
        document.delete()
        messages.success(request, "Document removed.")
    return redirect('vendors:vendor_detail', slug=vendor.slug)


@role_required(*CONTRACT_ROLES)
def vendor_contract_create(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if request.method == 'POST':
        form = VendorContractForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.vendor = vendor
            contract.created_by = request.user
            contract.save()
            messages.success(request, "Contract created.")
            return redirect('vendors:vendor_contract_detail', pk=contract.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VendorContractForm(user=request.user)
    return render(request, 'vendors/vendor_contract_form.html', {'form': form, 'vendor': vendor})


@login_required
def vendor_contract_detail(request, pk):
    contract = get_object_or_404(VendorContract, pk=pk)
    can_manage = _can_manage_contract(request.user, contract)
    is_owner = _owns_vendor(request.user, contract.vendor)
    if not (can_manage or is_owner):
        messages.error(request, "You don't have permission to view this contract.")
        return redirect('vendors:vendor_detail', slug=contract.vendor.slug)

    status_form = VendorContractStatusForm(instance=contract)
    payment_form = VendorPaymentForm(vendor=contract.vendor, initial={'contract': contract})
    context = {
        'contract': contract,
        'status_form': status_form,
        'payment_form': payment_form,
        'can_manage': can_manage,
        'is_owner': is_owner,
        'payments': contract.payments.all(),
    }
    return render(request, 'vendors/vendor_contract_detail.html', context)


@login_required
def vendor_contract_update_status(request, pk):
    contract = get_object_or_404(VendorContract, pk=pk)
    if not _can_manage_contract(request.user, contract):
        messages.error(request, "You don't have permission to update this contract.")
        return redirect('vendors:vendor_contract_detail', pk=pk)
    if request.method == 'POST':
        form = VendorContractStatusForm(request.POST, instance=contract)
        if form.is_valid():
            contract = form.save(commit=False)
            if contract.status == 'signed' and not contract.signed_at:
                contract.signed_at = timezone.now()
            contract.save()
            messages.success(request, "Contract status updated.")
    return redirect('vendors:vendor_contract_detail', pk=pk)


@role_required(*CONTRACT_ROLES)
def vendor_rating_create(request, slug):
    vendor = get_object_or_404(VendorProfile, slug=slug)
    if request.method == 'POST':
        form = VendorRatingForm(request.POST, user=request.user)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.vendor = vendor
            rating.rated_by = request.user
            rating.save()
            messages.success(request, "Rating submitted.")
            return redirect('vendors:vendor_detail', slug=vendor.slug)
        messages.error(request, "Please correct the errors below.")
    else:
        form = VendorRatingForm(user=request.user)
    return render(request, 'vendors/vendor_rating_form.html', {'form': form, 'vendor': vendor})


@login_required
def vendor_payment_create(request, pk):
    contract = get_object_or_404(VendorContract, pk=pk)
    if not _can_manage_contract(request.user, contract):
        messages.error(request, "You don't have permission to record payments for this contract.")
        return redirect('vendors:vendor_contract_detail', pk=pk)
    if request.method == 'POST':
        form = VendorPaymentForm(request.POST, vendor=contract.vendor)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.vendor = contract.vendor
            payment.recorded_by = request.user
            payment.save()
            messages.success(request, "Payment recorded.")
        else:
            messages.error(request, "Please correct the errors below.")
    return redirect('vendors:vendor_contract_detail', pk=pk)


@login_required
def vendor_payment_list(request):
    payments = VendorPayment.objects.select_related('vendor', 'contract', 'contract__event').all()
    if not (request.user.is_super_admin or request.user.is_staff_role):
        if request.user.role != User.ORGANIZER:
            messages.error(request, "You don't have permission to view vendor payments.")
            return redirect('dashboard:dashboard')
        # Organizer sees only payments tied to contracts they created or
        # whose linked event they organize — never another Organizer's.
        payments = payments.filter(
            Q(contract__created_by=request.user) | Q(contract__event__organizer=request.user)
        )
    return render(request, 'vendors/vendor_payment_list.html', {'payments': payments})
