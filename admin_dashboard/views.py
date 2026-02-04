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
        'recent_activities': ActivityLog.objects.all().order_by('-created_at')[:10],

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

    users = User.objects.all().order_by('-date_joined')

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

    # Get querysets for display
    metal_types_qs = MetalType.objects.all()
    metal_purities_qs = MetalPurity.objects.all()
    product_categories_qs = ProductCategory.objects.all()
    stone_types_qs = StoneType.objects.all()
    payment_methods_qs = PaymentMethod.objects.all()
    bank_accounts_qs = BankAccount.objects.all()

    context = {
        'page_title': 'Configuration Système',
        'section': 'configuration',

        # Counts for display in cards
        'metal_types_count': metal_types_qs.count(),
        'metal_purities_count': metal_purities_qs.count(),
        'product_categories_count': product_categories_qs.count(),
        'stone_types_count': stone_types_qs.count(),
        'payment_methods_count': payment_methods_qs.count(),
        'bank_accounts_count': bank_accounts_qs.count(),

        # QuerySets for detailed lists
        'metal_types': metal_types_qs,
        'metal_purities': metal_purities_qs,
        'product_categories': product_categories_qs,
        'stone_types': stone_types_qs,
        'payment_methods': payment_methods_qs,
        'bank_accounts': bank_accounts_qs,
    }

    return render(request, 'admin_dashboard/configuration.html', context)


@login_required(login_url='login')
@staff_required
def activity_log_view(request):
    """Activity Log - View and filter system activity"""

    # Get all activities
    activities = ActivityLog.objects.all().order_by('-created_at')

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
        activities = activities.filter(model_name=object_type)

    # Date filter
    try:
        days_back = int(days)
        since_date = timezone.now() - timedelta(days=days_back)
        activities = activities.filter(created_at__gte=since_date)
    except (ValueError, TypeError):
        pass

    # Get available filters
    available_actions = ActivityLog.objects.values_list('action', flat=True).distinct()
    available_users = User.objects.filter(activity_logs__isnull=False).distinct()
    available_object_types = ActivityLog.objects.values_list(
        'model_name', flat=True
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
        ).order_by('-created_at')[:10],
    }

    return render(request, 'admin_dashboard/status.html', context)


@login_required(login_url='login')
@staff_required
def metal_type_create(request):
    """Create new metal type"""
    from admin_dashboard.forms import MetalTypeForm

    if request.method == 'POST':
        form = MetalTypeForm(request.POST)
        if form.is_valid():
            metal_type = form.save()
            messages.success(request, f'Type de métal "{metal_type.name}" créé avec succès.')
            return redirect('admin_dashboard:configuration')
    else:
        form = MetalTypeForm()

    context = {
        'page_title': 'Créer Type de Métal',
        'section': 'configuration',
        'form': form,
        'is_create': True,
    }

    return render(request, 'admin_dashboard/config/metal_type_form.html', context)


@login_required(login_url='login')
@staff_required
def metal_type_edit(request, pk):
    """Edit metal type"""
    from admin_dashboard.forms import MetalTypeForm
    from settings_app.models import MetalType

    metal_type = get_object_or_404(MetalType, pk=pk)

    if request.method == 'POST':
        form = MetalTypeForm(request.POST, instance=metal_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'Type de métal "{metal_type.name}" mis à jour.')
            return redirect('admin_dashboard:configuration')
    else:
        form = MetalTypeForm(instance=metal_type)

    context = {
        'page_title': f'Éditer {metal_type.name}',
        'section': 'configuration',
        'form': form,
        'is_create': False,
        'object': metal_type,
    }

    return render(request, 'admin_dashboard/config/metal_type_form.html', context)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def metal_type_delete(request, pk):
    """Delete metal type"""
    from settings_app.models import MetalType

    metal_type = get_object_or_404(MetalType, pk=pk)
    name = metal_type.name
    metal_type.delete()
    messages.success(request, f'Type de métal "{name}" supprimé.')

    return redirect('admin_dashboard:configuration')


@login_required(login_url='login')
@staff_required
def payment_method_create(request):
    """Create new payment method"""
    from admin_dashboard.forms import PaymentMethodForm

    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            payment_method = form.save()
            messages.success(request, f'Mode de paiement "{payment_method.name}" créé avec succès.')
            return redirect('admin_dashboard:configuration')
    else:
        form = PaymentMethodForm()

    context = {
        'page_title': 'Créer Mode de Paiement',
        'section': 'configuration',
        'form': form,
        'is_create': True,
    }

    return render(request, 'admin_dashboard/config/payment_method_form.html', context)


@login_required(login_url='login')
@staff_required
def payment_method_edit(request, pk):
    """Edit payment method"""
    from admin_dashboard.forms import PaymentMethodForm
    from settings_app.models import PaymentMethod

    payment_method = get_object_or_404(PaymentMethod, pk=pk)

    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=payment_method)
        if form.is_valid():
            form.save()
            messages.success(request, f'Mode de paiement "{payment_method.name}" mis à jour.')
            return redirect('admin_dashboard:configuration')
    else:
        form = PaymentMethodForm(instance=payment_method)

    context = {
        'page_title': f'Éditer {payment_method.name}',
        'section': 'configuration',
        'form': form,
        'is_create': False,
        'object': payment_method,
    }

    return render(request, 'admin_dashboard/config/payment_method_form.html', context)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def payment_method_delete(request, pk):
    """Delete payment method"""
    from settings_app.models import PaymentMethod

    payment_method = get_object_or_404(PaymentMethod, pk=pk)
    name = payment_method.name
    payment_method.delete()
    messages.success(request, f'Mode de paiement "{name}" supprimé.')

    return redirect('admin_dashboard:configuration')


@login_required(login_url='login')
@staff_required
def product_category_create(request):
    """Create new product category"""
    from admin_dashboard.forms import ProductCategoryForm

    if request.method == 'POST':
        form = ProductCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Catégorie "{category.name}" créée avec succès.')
            return redirect('admin_dashboard:configuration')
    else:
        form = ProductCategoryForm()

    context = {
        'page_title': 'Créer Catégorie',
        'section': 'configuration',
        'form': form,
        'is_create': True,
    }

    return render(request, 'admin_dashboard/config/category_form.html', context)


@login_required(login_url='login')
@staff_required
def product_category_edit(request, pk):
    """Edit product category"""
    from admin_dashboard.forms import ProductCategoryForm
    from settings_app.models import ProductCategory

    category = get_object_or_404(ProductCategory, pk=pk)

    if request.method == 'POST':
        form = ProductCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'Catégorie "{category.name}" mise à jour.')
            return redirect('admin_dashboard:configuration')
    else:
        form = ProductCategoryForm(instance=category)

    context = {
        'page_title': f'Éditer {category.name}',
        'section': 'configuration',
        'form': form,
        'is_create': False,
        'object': category,
    }

    return render(request, 'admin_dashboard/config/category_form.html', context)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def product_category_delete(request, pk):
    """Delete product category"""
    from settings_app.models import ProductCategory

    category = get_object_or_404(ProductCategory, pk=pk)
    name = category.name
    category.delete()
    messages.success(request, f'Catégorie "{name}" supprimée.')

    return redirect('admin_dashboard:configuration')


@login_required(login_url='login')
@staff_required
def bank_account_create(request):
    """Create new bank account"""
    from admin_dashboard.forms import BankAccountForm

    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(request, f'Compte bancaire "{account.bank_name}" créé avec succès.')
            return redirect('admin_dashboard:configuration')
    else:
        form = BankAccountForm()

    context = {
        'page_title': 'Créer Compte Bancaire',
        'section': 'configuration',
        'form': form,
        'is_create': True,
    }

    return render(request, 'admin_dashboard/config/bank_account_form.html', context)


@login_required(login_url='login')
@staff_required
def bank_account_edit(request, pk):
    """Edit bank account"""
    from admin_dashboard.forms import BankAccountForm
    from settings_app.models import BankAccount

    account = get_object_or_404(BankAccount, pk=pk)

    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, f'Compte bancaire "{account.bank_name}" mis à jour.')
            return redirect('admin_dashboard:configuration')
    else:
        form = BankAccountForm(instance=account)

    context = {
        'page_title': f'Éditer {account.bank_name}',
        'section': 'configuration',
        'form': form,
        'is_create': False,
        'object': account,
    }

    return render(request, 'admin_dashboard/config/bank_account_form.html', context)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def bank_account_delete(request, pk):
    """Delete bank account"""
    from settings_app.models import BankAccount

    account = get_object_or_404(BankAccount, pk=pk)
    name = account.bank_name
    account.delete()
    messages.success(request, f'Compte bancaire "{name}" supprimé.')

    return redirect('admin_dashboard:configuration')


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
