from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import Quote, QuoteItem


class QuoteItemInline(admin.TabularInline):
    """Inline admin for quote items"""
    model = QuoteItem
    extra = 1
    fields = ('description', 'quantity', 'unit_price_dh', 'line_total_dh')
    readonly_fields = ('line_total_dh',)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    """Admin for quotes"""
    list_display = ('reference', 'client', 'status_badge', 'total_amount_dh',
                   'issued_date', 'valid_until_date')
    list_filter = ('status', 'issued_date', 'valid_until_date')
    search_fields = ('reference', 'client__name')
    readonly_fields = ('created_at', 'updated_at', 'total_amount_dh',
                      'discount_amount_dh', 'created_by')
    inlines = (QuoteItemInline,)

    fieldsets = (
        (_('Référence'), {
            'fields': ('reference', 'status')
        }),
        (_('Client'), {
            'fields': ('client', 'contact_person')
        }),
        (_('Détails'), {
            'fields': ('description', 'specifications')
        }),
        (_('Montants'), {
            'fields': ('subtotal_dh', 'discount_percent', 'discount_amount_dh',
                      'tax_amount_dh', 'total_amount_dh')
        }),
        (_('Validité'), {
            'fields': ('issued_date', 'valid_until_date')
        }),
        (_('Conversion'), {
            'fields': ('converted_sale',),
            'classes': ('collapse',)
        }),
        (_('Conditions'), {
            'fields': ('terms_conditions', 'notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        """Display quote status"""
        colors = {
            'draft': '#95a5a6',
            'sent': '#3498db',
            'accepted': '#2ecc71',
            'rejected': '#e74c3c',
            'expired': '#34495e',
            'converted': '#27ae60'
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = _('Statut')


@admin.register(QuoteItem)
class QuoteItemAdmin(admin.ModelAdmin):
    """Admin for quote items"""
    list_display = ('quote', 'description', 'quantity', 'unit_price_dh', 'line_total_dh')
    list_filter = ('quote',)
    search_fields = ('quote__reference', 'description')
    readonly_fields = ('line_total_dh',)
