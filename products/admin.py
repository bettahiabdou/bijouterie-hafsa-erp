from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import Product, ProductImage, ProductStone, RawMaterial, RawMaterialMovement


class ProductImageInline(admin.TabularInline):
    """Inline admin for product images"""
    model = ProductImage
    extra = 1


class ProductStoneInline(admin.TabularInline):
    """Inline admin for product stones"""
    model = ProductStone
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Professional admin interface for Product management"""

    list_display = ('reference', 'name', 'category', 'status_badge', 'metal_type',
                   'gross_weight', 'selling_price')
    list_filter = ('product_type', 'status', 'category', 'metal_type', 'created_at')
    search_fields = ('reference', 'name', 'barcode', 'rfid_tag', 'description')
    readonly_fields = ('created_at', 'updated_at')
    inlines = (ProductImageInline, ProductStoneInline)

    fieldsets = (
        (_('Identification'), {
            'fields': ('reference', 'barcode', 'rfid_tag')
        }),
        (_('Informations générales'), {
            'fields': ('name', 'name_ar', 'description', 'product_type', 'category')
        }),
        (_('Métaux et poids'), {
            'fields': ('metal_type', 'metal_purity', 'gross_weight', 'net_weight')
        }),
        (_('Tarification'), {
            'fields': ('purchase_price_per_gram', 'metal_cost', 'labor_cost',
                      'stone_cost', 'other_cost', 'total_cost', 'selling_price', 'minimum_price')
        }),
        (_('Stock et statut'), {
            'fields': ('status', 'location')
        }),
        (_('Notes'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        """Display status as a colored badge"""
        colors = {
            'available': '#2ecc71',
            'reserved': '#f39c12',
            'sold': '#95a5a6',
            'in_repair': '#3498db',
            'consigned_in': '#9b59b6',
            'consigned_out': '#1abc9c',
            'returned': '#e74c3c',
            'custom_order': '#34495e'
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = _('Statut')


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Admin for product images"""
    list_display = ('product', 'image_preview', 'is_primary')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        """Show image thumbnail"""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 100px;"/>',
                obj.image.url
            )
        return '-'
    image_preview.short_description = _('Aperçu')


@admin.register(ProductStone)
class ProductStoneAdmin(admin.ModelAdmin):
    """Admin for stones in products"""
    list_display = ('product', 'stone_type')
    list_filter = ('stone_type', 'product')
    search_fields = ('product__name',)


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    """Admin for raw materials"""
    list_display = ('metal_type', 'metal_purity', 'current_weight',
                   'average_cost_per_gram', 'location')
    list_filter = ('metal_type', 'metal_purity', 'location')
    search_fields = ('metal_type__name',)
    readonly_fields = ('last_updated',)


@admin.register(RawMaterialMovement)
class RawMaterialMovementAdmin(admin.ModelAdmin):
    """Admin for raw material stock movements"""
    list_display = ('raw_material', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('raw_material__metal_type__name',)
    readonly_fields = ('created_at',)
