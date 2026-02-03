"""
Main views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from users.models import ActivityLog


@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Log activity
            ActivityLog.objects.create(
                user=user,
                action=ActivityLog.ActionType.LOGIN,
                ip_address=get_client_ip(request)
            )

            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Nom d\'utilisateur ou mot de passe invalide.')

    return render(request, 'login.html')


@login_required(login_url='login')
def logout_view(request):
    """User logout view"""
    user = request.user
    logout(request)

    # Log activity
    ActivityLog.objects.create(
        user=user,
        action=ActivityLog.ActionType.LOGOUT,
        ip_address=get_client_ip(request)
    )

    messages.success(request, 'Vous avez été déconnecté avec succès.')
    return redirect('login')


@login_required(login_url='login')
def dashboard(request):
    """Main dashboard view"""
    context = {
        'page_title': 'Tableau de Bord',
        'activities': [],  # Will be populated with recent activity logs
    }
    return render(request, 'dashboard.html', context)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
