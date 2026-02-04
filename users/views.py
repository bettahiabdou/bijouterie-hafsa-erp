"""
User management views for Bijouterie Hafsa ERP
Handles user profiles, passwords, and activity logs
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q, Count
from datetime import timedelta
from django.utils.timezone import now

from .models import User, ActivityLog


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
def profile_view(request):
    """View user profile"""
    user = request.user

    # Get user statistics
    seven_days_ago = now() - timedelta(days=7)
    stats = {
        'total_activities': ActivityLog.objects.filter(user=user).count(),
        'recent_activities': ActivityLog.objects.filter(user=user, timestamp__gte=seven_days_ago).count(),
        'last_login': ActivityLog.objects.filter(
            user=user,
            action='login'
        ).order_by('-timestamp').first(),
        'role': user.get_role_display() if hasattr(user, 'get_role_display') else user.role,
    }

    context = {
        'user': user,
        'stats': stats,
    }
    return render(request, 'users/profile.html', context)


@login_required
def profile_edit(request):
    """Edit user profile"""
    user = request.user

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()

        # Log activity
        ActivityLog.objects.create(
            user=user,
            action='update',
            object_type='User',
            object_id=user.id,
            description=f'Updated profile',
            ip_address=get_client_ip(request)
        )

        messages.success(request, 'Profil mis à jour avec succès.')
        return redirect('users:profile')

    context = {
        'user': user,
    }
    return render(request, 'users/profile_edit.html', context)


@login_required
def password_change(request):
    """Change user password"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)

            # Log activity
            ActivityLog.objects.create(
                user=user,
                action='update',
                object_type='User',
                object_id=user.id,
                description='Changed password',
                ip_address=get_client_ip(request)
            )

            messages.success(request, 'Votre mot de passe a été changé avec succès.')
            return redirect('users:profile')
        else:
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = PasswordChangeForm(request.user)

    context = {
        'form': form,
    }
    return render(request, 'users/password_change.html', context)


@login_required
def activity_log(request):
    """View user activity log"""
    user = request.user
    logs = ActivityLog.objects.filter(user=user).order_by('-timestamp')

    # Filter by action type
    action = request.GET.get('action', '')
    if action:
        logs = logs.filter(action=action)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        logs = logs.filter(timestamp__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__lte=date_to)

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)

    context = {
        'logs': logs_page,
        'action': action,
        'date_from': date_from,
        'date_to': date_to,
        'action_choices': ActivityLog.ActionType.choices,
    }
    return render(request, 'users/activity_log.html', context)


@login_required
@permission_required('users.view_user', raise_exception=True)
def user_list(request):
    """List all users (admin only)"""
    users = User.objects.all()

    # Search by name or email
    search = request.GET.get('search', '')
    if search:
        users = users.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(username__icontains=search)
        )

    # Filter by role
    role = request.GET.get('role', '')
    if role:
        users = users.filter(role=role)

    # Filter by active status
    status = request.GET.get('status', '')
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    # Statistics
    stats = {
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'inactive': User.objects.filter(is_active=False).count(),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(users.order_by('-date_joined'), 20)
    page = request.GET.get('page', 1)
    users_page = paginator.get_page(page)

    context = {
        'users': users_page,
        'search': search,
        'role': role,
        'status': status,
        'stats': stats,
        'role_choices': User.Role.choices if hasattr(User, 'Role') else [],
    }
    return render(request, 'users/user_list.html', context)


@login_required
@permission_required('users.view_user', raise_exception=True)
def user_detail(request, user_id):
    """View user details (admin only)"""
    user = get_object_or_404(User, id=user_id)

    # Get user statistics
    stats = {
        'total_activities': ActivityLog.objects.filter(user=user).count(),
        'last_login': ActivityLog.objects.filter(
            user=user,
            action='login'
        ).order_by('-timestamp').first(),
        'activities_7days': ActivityLog.objects.filter(
            user=user,
            timestamp__gte=now() - timedelta(days=7)
        ).count(),
    }

    # Get recent activities
    recent_activities = ActivityLog.objects.filter(user=user).order_by('-timestamp')[:10]

    context = {
        'user': user,
        'stats': stats,
        'recent_activities': recent_activities,
    }
    return render(request, 'users/user_detail.html', context)


@login_required
@permission_required('users.change_user', raise_exception=True)
def user_edit(request, user_id):
    """Edit user (admin only)"""
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.is_active = request.POST.get('is_active') == 'on'

        if hasattr(user, 'role'):
            user.role = request.POST.get('role', user.role)

        user.save()

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action='update',
            object_type='User',
            object_id=user.id,
            description=f'Edited user {user.get_full_name()}',
            ip_address=get_client_ip(request)
        )

        messages.success(request, f'Utilisateur {user.get_full_name()} mis à jour.')
        return redirect('users:user_detail', user_id=user.id)

    context = {
        'user': user,
        'role_choices': User.Role.choices if hasattr(User, 'Role') else [],
    }
    return render(request, 'users/user_edit.html', context)


@login_required
@permission_required('users.delete_user', raise_exception=True)
def user_deactivate(request, user_id):
    """Deactivate user (admin only)"""
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        user.is_active = False
        user.save()

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action='update',
            object_type='User',
            object_id=user.id,
            description=f'Deactivated user {user.get_full_name()}',
            ip_address=get_client_ip(request)
        )

        messages.success(request, f'Utilisateur {user.get_full_name()} désactivé.')
        return redirect('users:user_list')

    context = {
        'user': user,
    }
    return render(request, 'users/user_deactivate.html', context)


@login_required
@permission_required('users.view_activitylog', raise_exception=True)
def activity_log_admin(request):
    """View all activity logs (admin only)"""
    logs = ActivityLog.objects.select_related('user').order_by('-timestamp')

    # Search by user
    search = request.GET.get('search', '')
    if search:
        logs = logs.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(description__icontains=search)
        )

    # Filter by action
    action = request.GET.get('action', '')
    if action:
        logs = logs.filter(action=action)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        logs = logs.filter(timestamp__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__lte=date_to)

    # Statistics
    today = now().date()
    stats = {
        'total': ActivityLog.objects.count(),
        'today': ActivityLog.objects.filter(timestamp__date=today).count(),
        'by_action': ActivityLog.objects.values('action').annotate(count=Count('id')),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)

    context = {
        'logs': logs_page,
        'search': search,
        'action': action,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'action_choices': ActivityLog.ActionType.choices,
    }
    return render(request, 'users/activity_log_admin.html', context)
