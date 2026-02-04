"""
URL routing for Quotes app
"""
from django.urls import path
from . import views

app_name = 'quotes'

urlpatterns = [
    path('', views.quote_dashboard, name='dashboard'),
    path('list/', views.quote_list, name='quote_list'),
    path('create/', views.quote_create, name='quote_create'),
    path('<str:reference>/', views.quote_detail, name='quote_detail'),
]
