from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import SaleInvoice, ClientLoan, Layaway


@admin.register(SaleInvoice)
class SaleInvoiceAdmin(admin.ModelAdmin):
    """Admin for sale invoices"""
    list_display = ('reference', 'client', 'total_amount', 'status_badge', 'date')
    list_filter = ('status', 'sale_type', 'date')
    search_fields = ('reference', 'client__first_name', 'client__last_name')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (_('Référence et client'), {
            'fields': ('reference', 'client', 'date')
        }),
        (_('Type et statut'), {
            'fields': ('sale_type', 'status')
        }),
        (_('Montants'), {
            'fields': ('subtotal', 'discount_percent', 'discount_amount',
                      'old_gold_amount', 'total_amount', 'amount_paid', 'balance_due')
        }),
        (_('Livraison'), {
            'fields': ('delivery_method', 'delivery_address', 'delivery_status',
                      'delivery_date', 'delivery_cost')
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
        """Display sale status"""
        colors = {
            'draft': '#95a5a6',
            'confirmed': '#3498db',
            'delivered': '#2ecc71',
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


@admin.register(ClientLoan)
class ClientLoanAdmin(admin.ModelAdmin):
    """Admin for client loans"""
    list_display = ('reference', 'client', 'deposit_amount', 'status', 'date')
    list_filter = ('status', 'date')
    search_fields = ('reference', 'client__first_name', 'client__last_name')
    readonly_fields = ('created_at', 'updated_at', 'total_value')


@admin.register(Layaway)
class LayawayAdmin(admin.ModelAdmin):
    """Admin for layaway (deferred purchase) agreements"""
    list_display = ('reference', 'client', 'balance_due', 'status', 'date')
    list_filter = ('status', 'date')
    search_fields = ('reference', 'client__first_name', 'client__last_name')
    readonly_fields = ('created_at', 'updated_at')
