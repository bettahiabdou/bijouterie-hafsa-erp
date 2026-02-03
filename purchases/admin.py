from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import PurchaseOrder, PurchaseInvoice, Consignment


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """Admin for purchase orders"""
    list_display = ('reference', 'supplier', 'total_amount', 'status_badge', 'created_at')
    list_filter = ('status', 'supplier', 'created_at')
    search_fields = ('reference', 'supplier__name')
    readonly_fields = ('created_at', 'updated_at')

    def status_badge(self, obj):
        """Display purchase order status"""
        colors = {
            'draft': '#95a5a6',
            'submitted': '#f39c12',
            'confirmed': '#3498db',
            'received': '#2ecc71',
            'cancelled': '#e74c3c'
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = _('Statut')


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    """Admin for purchase invoices"""
    list_display = ('reference', 'supplier', 'total_amount', 'status_badge', 'created_at')
    list_filter = ('status', 'supplier', 'created_at')
    search_fields = ('reference', 'supplier__name')
    readonly_fields = ('created_at', 'updated_at')

    def status_badge(self, obj):
        """Display purchase invoice status"""
        colors = {
            'draft': '#95a5a6',
            'confirmed': '#3498db',
            'received': '#2ecc71',
            'returned': '#e74c3c'
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = _('Statut')


@admin.register(Consignment)
class ConsignmentAdmin(admin.ModelAdmin):
    """Admin for consignments"""
    list_display = ('reference', 'supplier', 'total_value', 'status_badge', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reference', 'supplier__name')
    readonly_fields = ('created_at', 'updated_at')

    def status_badge(self, obj):
        """Display consignment status"""
        colors = {
            'active': '#3498db',
            'returned': '#2ecc71',
            'partially_returned': '#f39c12'
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = _('Statut')
