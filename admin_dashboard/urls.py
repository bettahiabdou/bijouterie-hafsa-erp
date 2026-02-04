"""
URL configuration for Admin Dashboard

All URLs are under /settings/ namespace: 'admin_dashboard'
"""

from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    # Admin Dashboard Home
    path('', views.admin_home, name='home'),

    # User Management
    path('users/', views.user_management, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/deactivate/', views.user_deactivate, name='user_deactivate'),

    # System Configuration
    path('configuration/', views.system_configuration, name='configuration'),

    # Generic Configuration CRUD Routes (DRY Implementation)
    # Supports all 15+ configuration model types dynamically
    path('config/<str:config_type>/create/', views.ConfigurationCreateView.as_view(), name='config_create'),
    path('config/<str:config_type>/<int:pk>/edit/', views.ConfigurationUpdateView.as_view(), name='config_edit'),
    path('config/<str:config_type>/<int:pk>/delete/', views.ConfigurationDeleteView.as_view(), name='config_delete'),

    # Legacy Metal Type Configuration (backward compatibility)
    path('metal-types/create/', views.metal_type_create, name='metal_type_create'),
    path('metal-types/<int:pk>/edit/', views.metal_type_edit, name='metal_type_edit'),
    path('metal-types/<int:pk>/delete/', views.metal_type_delete, name='metal_type_delete'),

    # Payment Method Configuration
    path('payment-methods/create/', views.payment_method_create, name='payment_method_create'),
    path('payment-methods/<int:pk>/edit/', views.payment_method_edit, name='payment_method_edit'),
    path('payment-methods/<int:pk>/delete/', views.payment_method_delete, name='payment_method_delete'),

    # Product Category Configuration
    path('categories/create/', views.product_category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.product_category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.product_category_delete, name='category_delete'),

    # Bank Account Configuration
    path('bank-accounts/create/', views.bank_account_create, name='bank_account_create'),
    path('bank-accounts/<int:pk>/edit/', views.bank_account_edit, name='bank_account_edit'),
    path('bank-accounts/<int:pk>/delete/', views.bank_account_delete, name='bank_account_delete'),

    # Activity Log
    path('activity/', views.activity_log_view, name='activity_log'),

    # System Status
    path('status/', views.system_status, name='status'),
]
