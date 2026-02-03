from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import ClientPayment, SupplierPayment, Deposit, PendingPayment


@admin.register(ClientPayment)
class ClientPaymentAdmin(admin.ModelAdmin):
    """Admin for client payments"""
    list_display = ('reference', 'client', 'amount', 'payment_method', 'date')
    list_filter = ('payment_method', 'date')
    search_fields = ('reference', 'client__first_name', 'client__last_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    """Admin for supplier payments"""
    list_display = ('reference', 'supplier', 'amount', 'payment_method', 'date')
    list_filter = ('payment_method', 'date')
    search_fields = ('reference', 'supplier__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    """Admin for deposits"""
    list_display = ('reference', 'deposit_type', 'amount_applied', 'status', 'date')
    list_filter = ('deposit_type', 'status', 'date')
    search_fields = ('reference',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PendingPayment)
class PendingPaymentAdmin(admin.ModelAdmin):
    """Admin for pending payments"""
    list_display = ('reference', 'party_type', 'amount_due', 'due_date', 'status')
    list_filter = ('party_type', 'due_date', 'status')
    search_fields = ('reference',)
    readonly_fields = ('created_at', 'updated_at')
