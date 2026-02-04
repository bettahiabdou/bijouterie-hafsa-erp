"""
URL routing for Clients app
"""
from django.urls import path
from . import views

app_name = 'clients'

urlpatterns = [
    path('quick-create/', views.quick_create_client, name='quick_create'),
]
