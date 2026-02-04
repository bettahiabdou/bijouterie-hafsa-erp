"""
URL routing for Suppliers app
"""
from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    # Supplier management
    path('', views.supplier_list, name='list'),
    path('create/', views.supplier_create, name='create'),
    path('<str:code>/', views.supplier_detail, name='detail'),
    path('<str:code>/edit/', views.supplier_edit, name='edit'),
    path('<str:code>/delete/', views.supplier_delete, name='delete'),
]
