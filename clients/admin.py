from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import Client, OldGoldPurchase


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """Admin for clients"""
    list_display = ('code', 'first_name', 'last_name', 'email', 'phone',
                   'is_active', 'loyalty_points')
    list_filter = ('is_active', 'client_type', 'created_at')
    search_fields = ('code', 'first_name', 'last_name', 'email', 'phone', 'cin')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (_('Informations personnelles'), {
            'fields': ('code', 'first_name', 'last_name', 'first_name_ar', 'last_name_ar',
                      'date_of_birth', 'wedding_anniversary')
        }),
        (_('Contact'), {
            'fields': ('phone', 'phone_2', 'email')
        }),
        (_('Adresse'), {
            'fields': ('address', 'city')
        }),
        (_('Identité'), {
            'fields': ('cin', 'client_type')
        }),
        (_('Préférences'), {
            'fields': ('preferred_metal', 'preferred_purity', 'preferences')
        }),
        (_('Crédit et fidélité'), {
            'fields': ('credit_limit', 'loyalty_points')
        }),
        (_('Statut'), {
            'fields': ('is_active', 'notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OldGoldPurchase)
class OldGoldPurchaseAdmin(admin.ModelAdmin):
    """Admin for old gold purchases"""
    list_display = ('reference', 'client', 'gross_weight', 'tested_purity', 'total_amount',
                   'created_at')
    list_filter = ('metal_type', 'created_at', 'client')
    search_fields = ('reference', 'client__first_name', 'client__last_name', 'client_name')
    readonly_fields = ('created_at', 'updated_at')
