"""
URL routing for Purchases app
"""
from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    # Purchase Orders
    path('orders/', views.purchase_order_list, name='purchase_order_list'),
    path('orders/create/', views.purchase_order_create, name='purchase_order_create'),
    path('orders/<str:reference>/', views.purchase_order_detail, name='purchase_order_detail'),

    # Purchase Invoices
    path('invoices/', views.purchase_invoice_list, name='purchase_invoice_list'),
    path('invoices/create/', views.purchase_invoice_create, name='purchase_invoice_create'),
    path('invoices/<str:reference>/', views.purchase_invoice_detail, name='purchase_invoice_detail'),

    # Consignments
    path('consignments/', views.consignment_list, name='consignment_list'),
    path('consignments/create/', views.consignment_create, name='consignment_create'),
    path('consignments/<str:reference>/', views.consignment_detail, name='consignment_detail'),
]
