"""
URL routing for Sales app
"""
from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.sales_dashboard, name='sales_dashboard'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/bulk-create/', views.bulk_invoice_create, name='bulk_create'),
    path('invoices/<str:reference>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<str:reference>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<str:reference>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<str:reference>/payment/', views.invoice_payment, name='invoice_payment'),
    path('invoices/<str:reference>/delivery/', views.invoice_delivery, name='invoice_delivery'),

    # Invoice Items (Add/Delete)
    path('invoices/<str:reference>/add-item/', views.add_invoice_item, name='add_item'),
    path('invoices/delete-item/', views.delete_invoice_item, name='delete_item'),

    # API endpoints
    path('api/payment-methods/', views.get_payment_methods, name='get_payment_methods'),
    path('api/search-products/', views.search_products_api, name='search_products_api'),

    # Quote to Invoice conversion
    path('quotes/<int:quote_id>/to-invoice/', views.quote_to_invoice, name='quote_to_invoice'),

    # Payment tracking
    path('payments/tracking/', views.payment_tracking, name='payment_tracking'),

    # Pending invoices (Brouillon - from Telegram)
    path('pending/', views.pending_invoices_list, name='pending_invoices'),
    path('pending/<str:reference>/complete/', views.pending_invoice_complete, name='pending_invoice_complete'),

    # Livraisons (Delivery Tracking)
    path('livraisons/', views.delivery_list, name='delivery_list'),
    path('livraisons/bulk-check/', views.delivery_bulk_check, name='delivery_bulk_check'),
    path('livraisons/<str:reference>/', views.delivery_detail, name='delivery_detail'),
    path('livraisons/<str:reference>/check/', views.delivery_check, name='delivery_check'),
    path('livraisons/<str:reference>/update-from-client/', views.delivery_update_from_client, name='delivery_update_from_client'),
]
