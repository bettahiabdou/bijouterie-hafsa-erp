"""
URL routing for Users app
"""
from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # User profile
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/password/', views.password_change, name='password_change'),
    path('activity/', views.activity_log, name='activity_log'),

    # Admin user management
    path('list/', views.user_list, name='user_list'),
    path('<int:user_id>/', views.user_detail, name='user_detail'),
    path('<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('<int:user_id>/deactivate/', views.user_deactivate, name='user_deactivate'),

    # Admin activity log
    path('activity/admin/', views.activity_log_admin, name='activity_log_admin'),
]
