from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Supplier, SupplierBankAccount, ArtisanJob


class SupplierBankAccountInline(admin.TabularInline):
    """Inline admin for supplier bank accounts"""
    model = SupplierBankAccount
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    """Admin for suppliers"""
    list_display = ('code', 'name', 'email', 'phone', 'city', 'is_active')
    list_filter = ('is_active', 'city', 'created_at')
    search_fields = ('code', 'name', 'email', 'phone', 'ice')
    readonly_fields = ('created_at', 'updated_at')
    inlines = (SupplierBankAccountInline,)

    fieldsets = (
        (_('Informations générales'), {
            'fields': ('code', 'name', 'name_ar', 'email', 'phone', 'phone_2')
        }),
        (_('Adresse'), {
            'fields': ('address', 'city')
        }),
        (_('Taxe et identification'), {
            'fields': ('ice', 'rc')
        }),
        (_('Conditions'), {
            'fields': ('payment_terms', 'credit_limit', 'specialty')
        }),
        (_('Statut'), {
            'fields': ('is_active', 'notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SupplierBankAccount)
class SupplierBankAccountAdmin(admin.ModelAdmin):
    """Admin for supplier bank accounts"""
    list_display = ('supplier', 'bank_name', 'account_number', 'is_default')
    list_filter = ('is_default', 'supplier')
    search_fields = ('supplier__name', 'account_number')


@admin.register(ArtisanJob)
class ArtisanJobAdmin(admin.ModelAdmin):
    """Admin for artisan jobs"""
    list_display = ('reference', 'artisan', 'status', 'date_sent', 'date_received')
    list_filter = ('status', 'created_at')
    search_fields = ('reference', 'artisan__name', 'description')
    readonly_fields = ('created_at', 'updated_at')
