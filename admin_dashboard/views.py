"""
Admin Dashboard Views for Bijouterie Hafsa ERP

Consolidated admin panel replacing Django admin with mobile-responsive interface.
All views require is_staff permission.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.contrib import messages
from decimal import Decimal
from datetime import timedelta

from users.models import ActivityLog, User
from sales.models import SaleInvoice
from purchases.models import PurchaseOrder
from repairs.models import Repair
from clients.models import Client
from suppliers.models import Supplier
from products.models import Product
from settings_app.models import (
    MetalType, MetalPurity, ProductCategory,
    StoneType, PaymentMethod, BankAccount
)


def staff_required(view_func):
    """Decorator to check if user is staff"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, 'Accès non autorisé. Vous devez être administrateur.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required(login_url='login')
@staff_required
def admin_home(request):
    """Admin Dashboard - Overview of system health and quick stats"""

    today = timezone.now().date()
    this_month = timezone.now().date().replace(day=1)

    context = {
        'page_title': 'Administration',
        'section': 'home',

        # System Statistics
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'staff_count': User.objects.filter(is_staff=True).count(),

        # Business Statistics
        'total_clients': Client.objects.count(),
        'total_suppliers': Supplier.objects.count(),
        'total_products': Product.objects.count(),
        'total_bank_accounts': BankAccount.objects.count(),

        # Today's Activity
        'invoices_today': SaleInvoice.objects.filter(date=today).count(),
        'repairs_today': Repair.objects.filter(created_at__date=today).count(),
        'purchase_orders_today': PurchaseOrder.objects.filter(date=today).count(),

        # This Month's Revenue
        'invoices_this_month': SaleInvoice.objects.filter(
            date__gte=this_month
        ).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0'),

        # Configuration Stats
        'metal_types': MetalType.objects.count(),
        'metal_purities': MetalPurity.objects.count(),
        'product_categories': ProductCategory.objects.count(),
        'payment_methods': PaymentMethod.objects.count(),

        # Recent Activity
        'recent_activities': ActivityLog.objects.all().order_by('-timestamp')[:10],

        # System Health
        'pending_repairs': Repair.objects.exclude(
            status__in=['completed', 'delivered', 'cancelled']
        ).count(),
        'pending_purchase_orders': PurchaseOrder.objects.exclude(
            status__in=['received', 'cancelled']
        ).count(),
    }

    return render(request, 'admin_dashboard/home.html', context)


@login_required(login_url='login')
@staff_required
def user_management(request):
    """User Management - List all users"""

    users = User.objects.all().order_by('-created_at')

    # Filter by role if provided
    role = request.GET.get('role')
    if role:
        users = users.filter(role=role)

    # Filter by status
    status = request.GET.get('status')
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    context = {
        'page_title': 'Gestion des Utilisateurs',
        'section': 'users',
        'users': users,
        'roles': User.Role.choices,
        'selected_role': role,
        'selected_status': status,
    }

    return render(request, 'admin_dashboard/users/list.html', context)


@login_required(login_url='login')
@staff_required
def user_create(request):
    """Create new user"""
    from admin_dashboard.forms import UserManagementForm

    if request.method == 'POST':
        form = UserManagementForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # Set password
            if request.POST.get('password'):
                user.set_password(request.POST.get('password'))
            # Auto-assign permissions based on role
            user.assign_permissions_by_role()
            user.save()
            messages.success(request, f'Utilisateur {user.full_name} créé avec succès.')
            return redirect('admin_dashboard:user_list')
    else:
        form = UserManagementForm()

    context = {
        'page_title': 'Créer Utilisateur',
        'section': 'users',
        'form': form,
        'is_create': True,
    }

    return render(request, 'admin_dashboard/users/form.html', context)


@login_required(login_url='login')
@staff_required
def user_edit(request, user_id):
    """Edit user details"""
    from admin_dashboard.forms import UserManagementForm

    user_obj = get_object_or_404(User, pk=user_id)

    # Prevent editing superusers (except by themselves or other superusers)
    if user_obj.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Vous ne pouvez pas modifier un superutilisateur.')
        return redirect('admin_dashboard:user_list')

    if request.method == 'POST':
        form = UserManagementForm(request.POST, instance=user_obj)
        if form.is_valid():
            user = form.save(commit=False)
            # Update password if provided
            if request.POST.get('password'):
                user.set_password(request.POST.get('password'))
            # Update permissions based on new role
            user.assign_permissions_by_role()
            user.save()
            messages.success(request, f'Utilisateur {user.full_name} mis à jour.')
            return redirect('admin_dashboard:user_list')
    else:
        form = UserManagementForm(instance=user_obj)

    context = {
        'page_title': f'Éditer {user_obj.full_name}',
        'section': 'users',
        'form': form,
        'user_obj': user_obj,
        'is_create': False,
    }

    return render(request, 'admin_dashboard/users/form.html', context)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def user_deactivate(request, user_id):
    """Deactivate user"""
    user_obj = get_object_or_404(User, pk=user_id)

    # Prevent deactivating superusers
    if user_obj.is_superuser:
        messages.error(request, 'Impossible de désactiver un superutilisateur.')
        return redirect('admin_dashboard:user_list')

    # Prevent deactivating yourself
    if user_obj.pk == request.user.pk:
        messages.error(request, 'Vous ne pouvez pas vous désactiver vous-même.')
        return redirect('admin_dashboard:user_list')

    user_obj.is_active = False
    user_obj.save()
    messages.success(request, f'Utilisateur {user_obj.full_name} désactivé.')

    # Log the action
    ActivityLog.objects.create(
        user=request.user,
        action='deactivate',
        object_type='user',
        object_id=user_obj.id,
        description=f'Désactivé par {request.user.full_name}',
        ip_address=get_client_ip(request),
    )

    return redirect('admin_dashboard:user_list')


@login_required(login_url='login')
@staff_required
def system_configuration(request):
    """System Configuration - Manage all system settings"""

    context = {
        'page_title': 'Configuration Système',
        'section': 'configuration',

        # Settings
        'metal_types': MetalType.objects.all(),
        'metal_purities': MetalPurity.objects.all(),
        'product_categories': ProductCategory.objects.all(),
        'stone_types': StoneType.objects.all(),
        'payment_methods': PaymentMethod.objects.all(),
        'bank_accounts': BankAccount.objects.all(),
    }

    return render(request, 'admin_dashboard/configuration.html', context)


@login_required(login_url='login')
@staff_required
def activity_log_view(request):
    """Activity Log - View and filter system activity"""

    # Get all activities
    activities = ActivityLog.objects.all().order_by('-timestamp')

    # Filters
    action = request.GET.get('action')
    user_id = request.GET.get('user')
    object_type = request.GET.get('object_type')
    days = request.GET.get('days', '7')  # Default last 7 days

    if action:
        activities = activities.filter(action=action)

    if user_id:
        activities = activities.filter(user_id=user_id)

    if object_type:
        activities = activities.filter(object_type=object_type)

    # Date filter
    try:
        days_back = int(days)
        since_date = timezone.now() - timedelta(days=days_back)
        activities = activities.filter(timestamp__gte=since_date)
    except (ValueError, TypeError):
        pass

    # Get available filters
    available_actions = ActivityLog.objects.values_list('action', flat=True).distinct()
    available_users = User.objects.filter(activitylog__isnull=False).distinct()
    available_object_types = ActivityLog.objects.values_list(
        'object_type', flat=True
    ).distinct()

    context = {
        'page_title': 'Journal d\'Activité',
        'section': 'activity',
        'activities': activities[:500],  # Limit display
        'available_actions': available_actions,
        'available_users': available_users,
        'available_object_types': available_object_types,

        # Selected filters
        'selected_action': action,
        'selected_user': user_id,
        'selected_object_type': object_type,
        'selected_days': days,
    }

    return render(request, 'admin_dashboard/activity_log.html', context)


@login_required(login_url='login')
@staff_required
def system_status(request):
    """System Status - Application health and diagnostics"""

    context = {
        'page_title': 'État du Système',
        'section': 'status',

        # Database stats
        'total_records': sum([
            Client.objects.count(),
            Supplier.objects.count(),
            Product.objects.count(),
            SaleInvoice.objects.count(),
            PurchaseOrder.objects.count(),
            Repair.objects.count(),
        ]),

        # User stats
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'admin_users': User.objects.filter(is_staff=True).count(),

        # Recent errors
        'recent_errors': ActivityLog.objects.filter(
            action='error'
        ).order_by('-timestamp')[:10],
    }

    return render(request, 'admin_dashboard/status.html', context)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
