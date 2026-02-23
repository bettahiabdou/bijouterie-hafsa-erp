from django.contrib import admin
from .models import StockStorageAccount, StockStorageItem


class StockStorageItemInline(admin.TabularInline):
    model = StockStorageItem
    extra = 0
    readonly_fields = ['stored_at', 'picked_up_at', 'picked_up_by', 'created_by']
    fields = ['product_reference', 'product_name', 'product_weight', 'price', 'status', 'stored_at', 'picked_up_at']


@admin.register(StockStorageAccount)
class StockStorageAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'get_waiting', 'get_total_value', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'client__phone', 'client__code']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    inlines = [StockStorageItemInline]

    def get_waiting(self, obj):
        return obj.waiting_items
    get_waiting.short_description = 'En attente'

    def get_total_value(self, obj):
        return f"{obj.total_value_waiting} DH"
    get_total_value.short_description = 'Valeur en attente'


@admin.register(StockStorageItem)
class StockStorageItemAdmin(admin.ModelAdmin):
    list_display = ['product_reference', 'product_name', 'account', 'price', 'status', 'stored_at', 'picked_up_at']
    list_filter = ['status', 'stored_at']
    search_fields = ['product_reference', 'product_name', 'account__client__first_name', 'account__client__last_name']
    readonly_fields = ['stored_at', 'picked_up_at', 'picked_up_by', 'created_by']
    raw_id_fields = ['account', 'invoice', 'product']
