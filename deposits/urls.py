"""
URL routing for Deposits app
"""
from django.urls import path
from . import views

app_name = 'deposits'

urlpatterns = [
    # Main views
    path('', views.deposit_list, name='list'),
    path('create/', views.deposit_create, name='create'),
    path('<int:pk>/', views.deposit_detail, name='detail'),

    # Account operations
    path('<int:pk>/add-fund/', views.add_fund, name='add_fund'),
    path('<int:pk>/withdrawal/', views.withdrawal, name='withdrawal'),
    path('<int:pk>/adjustment/', views.adjustment, name='adjustment'),

    # Purchase
    path('<int:pk>/purchase/', views.purchase_page, name='purchase'),
    path('<int:pk>/make-purchase/', views.make_purchase, name='make_purchase'),

    # API endpoints
    path('api/client/<int:client_id>/balance/', views.api_client_balance, name='api_client_balance'),
    path('api/product/<int:product_id>/', views.api_product_info, name='api_product_info'),
]
