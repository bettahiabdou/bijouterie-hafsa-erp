from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import Repair


@admin.register(Repair)
class RepairAdmin(admin.ModelAdmin):
    """Admin for repairs"""
    list_display = ('reference', 'client', 'status_badge', 'priority_badge',
                   'total_cost_dh', 'estimated_completion_date')
    list_filter = ('status', 'priority', 'repair_type', 'received_date')
    search_fields = ('reference', 'client__name', 'issue_description')
    readonly_fields = ('created_at', 'updated_at', 'total_cost_dh')

    fieldsets = (
        (_('Référence'), {
            'fields': ('reference',)
        }),
        (_('Client et article'), {
            'fields': ('client', 'product', 'item_description')
        }),
        (_('Détails de la réparation'), {
            'fields': ('repair_type', 'issue_description', 'repair_notes')
        }),
        (_('Coûts'), {
            'fields': ('assessment_cost_dh', 'labor_cost_dh',
                      'material_cost_dh', 'total_cost_dh')
        }),
        (_('Statut et priorité'), {
            'fields': ('status', 'priority')
        }),
        (_('Dates'), {
            'fields': ('received_date', 'estimated_completion_date',
                      'completion_date', 'delivery_date')
        }),
        (_('Assignation'), {
            'fields': ('assigned_to',)
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        """Display repair status"""
        colors = {
            'received': '#3498db',
            'assessing': '#f39c12',
            'approved': '#2ecc71',
            'in_progress': '#9b59b6',
            'completed': '#27ae60',
            'delivered': '#1abc9c',
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

    def priority_badge(self, obj):
        """Display repair priority"""
        colors = {
            'low': '#95a5a6',
            'medium': '#3498db',
            'high': '#f39c12',
            'urgent': '#e74c3c'
        }
        color = colors.get(obj.priority, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_priority_display()
        )
    priority_badge.short_description = _('Priorité')
