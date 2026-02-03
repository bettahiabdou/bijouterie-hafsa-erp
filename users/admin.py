from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import User, ActivityLog


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    Professional admin interface for User management
    """
    list_display = ('username', 'get_full_name', 'role_badge', 'email', 'is_active')
    list_filter = ('role', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('-date_joined',)

    fieldsets = (
        (_('Informations personnelles'), {
            'fields': ('username', 'first_name', 'last_name', 'email', 'phone')
        }),
        (_('Rôle et permissions'), {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser'),
            'classes': ('wide',)
        }),
        (_('Permissions de vente'), {
            'fields': (
                'can_view_purchase_cost',
                'can_give_discount',
                'max_discount_percent',
                'can_sell_below_cost',
                'can_approve_discount'
            ),
            'description': _('Contrôlez les permissions de vente de cet utilisateur')
        }),
        (_('Permissions de gestion'), {
            'fields': (
                'can_create_purchase_order',
                'can_delete_invoices',
                'can_manage_users',
                'can_view_reports',
                'can_manage_stock'
            ),
            'description': _('Contrôlez les permissions administratives')
        }),
        (_('Informations de compte'), {
            'fields': ('date_joined', 'last_login'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('date_joined', 'last_login')

    def role_badge(self, obj):
        """Display role as a colored badge"""
        colors = {
            'admin': '#e74c3c',
            'manager': '#3498db',
            'seller': '#2ecc71',
            'cashier': '#f39c12'
        }
        color = colors.get(obj.role, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_role_display()
        )
    role_badge.short_description = _('Rôle')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """
    Read-only admin for activity log viewing
    """
    list_display = ('user', 'action_badge', 'model_name', 'object_repr', 'created_at')
    list_filter = ('action', 'user', 'created_at', 'model_name')
    search_fields = ('user__username', 'object_repr', 'model_name')
    ordering = ('-created_at',)
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'object_repr',
                      'details', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def action_badge(self, obj):
        """Display action as a colored badge"""
        colors = {
            'login': '#2ecc71',
            'logout': '#95a5a6',
            'create': '#3498db',
            'update': '#f39c12',
            'delete': '#e74c3c',
            'view': '#9b59b6',
            'print': '#1abc9c',
            'export': '#34495e',
            'approve': '#27ae60',
            'reject': '#c0392b'
        }
        color = colors.get(obj.action, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_badge.short_description = _('Action')
