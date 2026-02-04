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
    path('invoices/<str:reference>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<str:reference>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<str:reference>/payment/', views.invoice_payment, name='invoice_payment'),
    path('invoices/<str:reference>/delivery/', views.invoice_delivery, name='invoice_delivery'),

    # Invoice Items (Add/Delete)
    path('invoices/<str:reference>/add-item/', views.add_invoice_item, name='add_item'),
    path('invoices/delete-item/', views.delete_invoice_item, name='delete_item'),

    # Quote to Invoice conversion
    path('quotes/<int:quote_id>/to-invoice/', views.quote_to_invoice, name='quote_to_invoice'),

    # Payment tracking
    path('payments/tracking/', views.payment_tracking, name='payment_tracking'),
]
