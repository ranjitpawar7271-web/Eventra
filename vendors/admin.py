from django.contrib import admin

from .models import VendorContract, VendorDocument, VendorPayment, VendorProfile, VendorRating, VendorService


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'service_type', 'status', 'user')
    list_filter = ('status', 'service_type')
    search_fields = ('company_name', 'user__username')
    prepopulated_fields = {'slug': ('company_name',)}


@admin.register(VendorService)
class VendorServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'price', 'price_unit', 'is_active')
    list_filter = ('is_active', 'price_unit')


@admin.register(VendorDocument)
class VendorDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'vendor', 'document_type', 'uploaded_at')
    list_filter = ('document_type',)


@admin.register(VendorContract)
class VendorContractAdmin(admin.ModelAdmin):
    list_display = ('title', 'vendor', 'event', 'amount', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(VendorRating)
class VendorRatingAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'service_quality', 'delivery_time', 'rated_by', 'created_at')


@admin.register(VendorPayment)
class VendorPaymentAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'amount', 'method', 'status', 'payment_date')
    list_filter = ('status', 'method')
