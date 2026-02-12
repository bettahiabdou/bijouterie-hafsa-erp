from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    MetalType, MetalPurity, ProductCategory, StoneType, StoneClarity,
    StoneColor, StoneCut, PaymentMethod, BankAccount, StockLocation,
    DeliveryMethod, DeliveryPerson, Carrier, RepairType
)


class ReadOnlyMixin:
    """Mixin to make admin read-only except for superuser"""
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(MetalType)
class MetalTypeAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for metal types"""
    list_display = ('name', 'code', 'is_active')
    search_fields = ('name', 'code')


@admin.register(MetalPurity)
class MetalPurityAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for metal purities"""
    list_display = ('name', 'purity_percentage', 'hallmark', 'metal_type')
    search_fields = ('name', 'hallmark')
    list_filter = ('metal_type',)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    """Admin for product categories"""
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(StoneType)
class StoneTypeAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for stone types"""
    list_display = ('name', 'code', 'is_precious')
    search_fields = ('name', 'code')


@admin.register(StoneClarity)
class StoneClarityAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for stone clarity"""
    list_display = ('name', 'code')
    search_fields = ('name',)


@admin.register(StoneColor)
class StoneColorAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for stone color"""
    list_display = ('name', 'code')
    search_fields = ('name',)


@admin.register(StoneCut)
class StoneCutAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for stone cut"""
    list_display = ('name', 'code')
    search_fields = ('name',)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for payment methods"""
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    """Admin for bank accounts"""
    list_display = ('bank_name', 'account_name', 'account_number', 'is_active')
    list_filter = ('is_active', 'bank_name')
    search_fields = ('account_number', 'account_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockLocation)
class StockLocationAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for stock locations"""
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(DeliveryMethod)
class DeliveryMethodAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for delivery methods"""
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(RepairType)
class RepairTypeAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Admin for repair types"""
    list_display = ('name', 'code', 'default_price')
    search_fields = ('name',)
    list_filter = ('is_active',)


@admin.register(DeliveryPerson)
class DeliveryPersonAdmin(admin.ModelAdmin):
    """Admin for delivery persons (internal)"""
    list_display = ('name', 'phone', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'phone')


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    """Admin for carriers/transporteurs (external)"""
    list_display = ('name', 'code', 'phone', 'supports_auto_tracking', 'is_active')
    list_filter = ('is_active', 'supports_auto_tracking')
    search_fields = ('name', 'code', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'phone')
        }),
        ('Options', {
            'fields': ('is_active', 'supports_auto_tracking', 'tracking_url_template')
        }),
        ('Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
