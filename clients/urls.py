"""
URL routing for Clients app
"""
from django.urls import path
from . import views

app_name = 'clients'

urlpatterns = [
    path('', views.client_list, name='list'),
    path('create/', views.client_create, name='create'),
    path('<int:pk>/', views.client_detail, name='detail'),
    path('<int:pk>/edit/', views.client_edit, name='edit'),
    path('<int:pk>/delete/', views.client_delete, name='delete'),
    path('quick-create/', views.quick_create_client, name='quick_create'),
]
