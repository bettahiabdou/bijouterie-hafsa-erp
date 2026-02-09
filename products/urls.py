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
    path('<str:reference>/', views.product_detail, name='detail'),
    path('<str:reference>/edit/', views.product_edit, name='edit'),
    path('<str:reference>/print/', views.print_label, name='print_label'),

    # Inventory
    path('inventory/dashboard/', views.inventory_dashboard, name='inventory_dashboard'),

    # Print
    path('print/test/', views.print_test, name='print_test'),
    path('print/debug/', views.printer_debug, name='printer_debug'),
]
