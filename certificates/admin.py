from django.contrib import admin

from .models import Certificate


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_code', 'cert_type', 'title', 'issued_at', 'revoked')
    list_filter = ('cert_type', 'revoked')
    search_fields = ('certificate_code', 'ticket__registration__user__username', 'ticket__registration__event__title')
