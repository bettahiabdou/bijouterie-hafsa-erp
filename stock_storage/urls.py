from django.urls import path
from . import views

app_name = 'stock_storage'

urlpatterns = [
    path('', views.storage_list, name='list'),
    path('dashboard/', views.storage_dashboard, name='dashboard'),
    path('<int:pk>/', views.storage_detail, name='detail'),
    path('<int:pk>/pickup-item/', views.pickup_item, name='pickup_item'),
    path('<int:pk>/bulk-pickup/', views.bulk_pickup, name='bulk_pickup'),
]
