"""
URL routing for Sales app
"""
from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/<str:reference>/', views.invoice_detail, name='invoice_detail'),

    # Quote to Invoice conversion
    path('quotes/<int:quote_id>/to-invoice/', views.quote_to_invoice, name='quote_to_invoice'),

    # Payment tracking
    path('payments/tracking/', views.payment_tracking, name='payment_tracking'),
]
