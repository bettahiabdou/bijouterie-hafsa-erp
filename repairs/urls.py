"""
URL routing for Repairs app
"""
from django.urls import path
from . import views

app_name = 'repairs'

urlpatterns = [
    path('', views.repair_dashboard, name='dashboard'),
    path('list/', views.repair_list, name='repair_list'),
    path('create/', views.repair_create, name='repair_create'),
    path('<str:reference>/', views.repair_detail, name='repair_detail'),
]
