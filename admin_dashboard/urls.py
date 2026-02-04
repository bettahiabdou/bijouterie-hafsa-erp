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

    # Activity Log
    path('activity/', views.activity_log_view, name='activity_log'),

    # System Status
    path('status/', views.system_status, name='status'),
]
