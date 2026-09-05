"""
URL routing for Sales app
"""
from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Dashboard & Insights
    path('dashboard/', views.sales_dashboard, name='sales_dashboard'),
    path('dashboard/export/', views.sales_export, name='sales_export'),
    path('dashboard/export-all/start/', views.full_export_start, name='full_export_start'),
    path('dashboard/export-all/<int:job_id>/status/', views.full_export_status, name='full_export_status'),
    path('dashboard/export-all/<int:job_id>/download/', views.full_export_download, name='full_export_download'),
    path('insights/', views.sales_insights, name='sales_insights'),
    path('api/insights-ai/', views.sales_insights_ai, name='sales_insights_ai'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/bulk-create/', views.bulk_invoice_create, name='bulk_create'),

    # Static invoice-item / photo routes — MUST come before the <reference>
    # catch-all below, otherwise 'update-item' etc. are matched as a reference (404).
    path('invoices/delete-item/', views.delete_invoice_item, name='delete_item'),
    path('invoices/update-item/', views.update_invoice_item, name='update_item'),
    path('invoices/photo/<int:photo_id>/delete/', views.delete_invoice_photo, name='delete_invoice_photo'),

    # Reference-based invoice routes (suffix'd sub-paths don't collide with <reference>)
    path('invoices/<str:reference>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<str:reference>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<str:reference>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<str:reference>/payment/', views.invoice_payment, name='invoice_payment'),
    path('invoices/<str:reference>/delivery/', views.invoice_delivery, name='invoice_delivery'),
    path('invoices/<str:reference>/add-item/', views.add_invoice_item, name='add_item'),
    path('invoices/<str:reference>/add-photo/', views.add_invoice_photo, name='add_invoice_photo'),

    # Payment editing
    path('api/update-payment/', views.update_payment, name='update_payment'),
    path('api/delete-payment/', views.delete_payment, name='delete_payment'),

    # API endpoints
    path('api/payment-methods/', views.get_payment_methods, name='get_payment_methods'),
    path('api/search-products/', views.search_products_api, name='search_products_api'),
    path('api/quick-create-client/', views.quick_create_client, name='quick_create_client'),
    path('api/ai-extract-sales/', views.ai_extract_sales_photo, name='ai_extract_sales'),

    # Quote to Invoice conversion
    path('quotes/<int:quote_id>/to-invoice/', views.quote_to_invoice, name='quote_to_invoice'),

    # Payments
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/tracking/', views.payment_tracking, name='payment_tracking'),

    # Pending invoices (Brouillon - from Telegram)
    path('pending/', views.pending_invoices_list, name='pending_invoices'),
    path('pending/<str:reference>/complete/', views.pending_invoice_complete, name='pending_invoice_complete'),
    path('pending/<str:reference>/api/', views.pending_invoice_detail_api, name='pending_invoice_detail_api'),
    path('pending/<str:reference>/complete/api/', views.pending_invoice_complete_api, name='pending_invoice_complete_api'),

    # Plateau anti-vol (anti-theft tray monitor)
    path('plateau/', views.tray_monitor, name='tray_monitor'),
    path('plateau/resolve/', views.tray_resolve, name='tray_resolve'),

    # Rapprochement AMANA (COD statement reconciliation)
    path('rapprochement-amana/', views.amana_reconciliation, name='amana_reconciliation'),
    path('rapprochement-amana/upload/', views.amana_statement_upload, name='amana_statement_upload'),
    path('rapprochement-amana/scan/', views.amana_ocr_page, name='amana_ocr_page'),
    path('rapprochement-amana/scan/analyze/', views.amana_ocr_analyze, name='amana_ocr_analyze'),
    path('rapprochement-amana/scan/status/', views.amana_ocr_status, name='amana_ocr_status'),
    path('rapprochement-amana/scan/import/', views.amana_ocr_import, name='amana_ocr_import'),
    path('rapprochement-amana/marquer-encaisse/', views.amana_mark_encaisse, name='amana_mark_encaisse'),
    path('rapprochement-amana/<int:pk>/supprimer/', views.amana_statement_delete, name='amana_statement_delete'),

    # Circulation (online-selling flow)
    path('circulation/', views.circulation_list, name='circulation'),
    path('circulation/search/', views.circulation_product_search, name='circulation_product_search'),
    path('circulation/scan/', views.circulation_scan_lookup, name='circulation_scan_lookup'),
    path('circulation/out/', views.circulation_out, name='circulation_out'),
    path('circulation/<int:pk>/return/', views.circulation_return, name='circulation_return'),
    path('circulation/<int:pk>/revert/', views.circulation_revert, name='circulation_revert'),

    # Bénéfice (profit report)
    path('benefice/', views.benefice_report, name='benefice'),
    path('benefice/print/', views.benefice_report_print, name='benefice_print'),

    # Poste Livraison (responsable AMANA workspace)
    path('poste-livraison/', views.delivery_desk, name='delivery_desk'),
    path('poste-livraison/<str:reference>/receptionner-retour/', views.delivery_desk_receive_return, name='delivery_desk_receive_return'),
    path('poste-livraison/<str:reference>/code/', views.delivery_desk_update_code, name='delivery_desk_update_code'),

    # Livraisons (Delivery Tracking)
    path('livraisons/', views.delivery_list, name='delivery_list'),
    path('livraisons/bulk-check/', views.delivery_bulk_check, name='delivery_bulk_check'),
    path('livraisons/<str:reference>/', views.delivery_detail, name='delivery_detail'),
    path('livraisons/<str:reference>/check/', views.delivery_check, name='delivery_check'),
    path('livraisons/<str:reference>/update-status/', views.delivery_update_status, name='delivery_update_status'),
    path('livraisons/<str:reference>/update-from-client/', views.delivery_update_from_client, name='delivery_update_from_client'),
]
