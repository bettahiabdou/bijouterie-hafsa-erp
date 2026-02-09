"""
Admin configuration for Deposits app
"""
from django.contrib import admin
from .models import DepositAccount, DepositTransaction


class DepositTransactionInline(admin.TabularInline):
    model = DepositTransaction
    extra = 0
    readonly_fields = ['created_at', 'created_by', 'balance_after']
    fields = ['transaction_type', 'amount', 'payment_method', 'description', 'balance_after', 'created_at', 'created_by']


@admin.register(DepositAccount)
class DepositAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'get_balance', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'client__phone', 'client__code']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    inlines = [DepositTransactionInline]

    def get_balance(self, obj):
        return f"{obj.balance} DH"
    get_balance.short_description = 'Solde'


@admin.register(DepositTransaction)
class DepositTransactionAdmin(admin.ModelAdmin):
    list_display = ['account', 'transaction_type', 'amount', 'balance_after', 'payment_method', 'created_at']
    list_filter = ['transaction_type', 'payment_method', 'created_at']
    search_fields = ['account__client__first_name', 'account__client__last_name', 'description']
    readonly_fields = ['created_at', 'created_by', 'balance_after']
    raw_id_fields = ['account', 'invoice', 'product']
