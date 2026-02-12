"""
URL routing for Products app
"""
from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Products
    path('', views.product_list, name='list'),
    path('create/', views.product_create, name='create'),
    path('batch-create/', views.batch_product_create, name='batch_create'),

    # Inventory
    path('inventory/dashboard/', views.inventory_dashboard, name='inventory_dashboard'),

    # Print (must be before <str:reference> catch-all)
    path('print/test/', views.print_test, name='print_test'),
    path('print/debug/', views.printer_debug, name='printer_debug'),
    path('print-queue/', views.print_queue_view, name='print_queue'),
    path('api/printer-config/', views.printer_config_api, name='printer_config_api'),
    path('api/print-queue/', views.print_queue_list, name='print_queue_list'),
    path('api/print-queue/pending/', views.print_queue_pending, name='print_queue_pending'),
    path('api/print-queue/<int:job_id>/complete/', views.print_queue_complete, name='print_queue_complete'),
    path('api/print-queue/<int:job_id>/fail/', views.print_queue_fail, name='print_queue_fail'),

    # Product detail routes (catch-all, must be last)
    path('<str:reference>/', views.product_detail, name='detail'),
    path('<str:reference>/edit/', views.product_edit, name='edit'),
    path('<str:reference>/delete/', views.product_delete, name='delete'),
    path('<str:reference>/print/', views.print_label, name='print_label'),
]
