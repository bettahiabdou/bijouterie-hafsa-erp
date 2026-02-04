"""
Admin Dashboard Views for Bijouterie Hafsa ERP

Consolidated admin panel replacing Django admin with mobile-responsive interface.
All views require is_staff permission.

Uses generic class-based views for DRY configuration management.
Supports 15+ configuration model types through dynamic registry.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse_lazy
from django.forms import ModelForm
from django.http import Http404
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
    MetalType, MetalPurity, ProductCategory, StoneType,
    StoneClarity, StoneColor, StoneCut, PaymentMethod,
    BankAccount, StockLocation, DeliveryMethod,
    DeliveryPerson, RepairType, CertificateIssuer,
    CompanySettings
)


def staff_required(view_func):
    """Decorator to check if user is staff"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, 'Accès non autorisé. Vous devez être administrateur.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ============================================================================
# CONFIGURATION MODEL REGISTRY & DYNAMIC FORM GENERATION
# ============================================================================

class ConfigurationRegistry:
    """
    Registry for all configuration models to support DRY CRUD operations.
    Centralizes model metadata, display settings, and field configurations.
    """

    MODELS = {
        'metal-types': {
            'model': MetalType,
            'label': 'Types de métaux',
            'singular': 'Type de métal',
            'fields': ['name', 'name_ar', 'code', 'is_active'],
            'list_display': ['name', 'code', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'metal-purities': {
            'model': MetalPurity,
            'label': 'Titres/Puretés',
            'singular': 'Titre/Pureté',
            'fields': ['metal_type', 'name', 'purity_percentage', 'hallmark', 'is_active'],
            'list_display': ['metal_type', 'name', 'purity_percentage', 'is_active'],
            'search_fields': ['name', 'hallmark'],
        },
        'categories': {
            'model': ProductCategory,
            'label': 'Catégories de produits',
            'singular': 'Catégorie',
            'fields': ['name', 'parent', 'code', 'description', 'is_active', 'display_order'],
            'list_display': ['name', 'code', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'stone-types': {
            'model': StoneType,
            'label': 'Types de pierres',
            'singular': 'Type de pierre',
            'fields': ['name', 'code', 'is_precious', 'requires_certificate', 'is_active'],
            'list_display': ['name', 'code', 'is_precious', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'stone-clarities': {
            'model': StoneClarity,
            'label': 'Clartés de pierres',
            'singular': 'Clarté',
            'fields': ['code', 'name', 'description', 'rank', 'is_active'],
            'list_display': ['code', 'name', 'rank', 'is_active'],
            'search_fields': ['code', 'name'],
        },
        'stone-colors': {
            'model': StoneColor,
            'label': 'Couleurs de pierres',
            'singular': 'Couleur',
            'fields': ['code', 'name', 'description', 'rank', 'is_active'],
            'list_display': ['code', 'name', 'rank', 'is_active'],
            'search_fields': ['code', 'name'],
        },
        'stone-cuts': {
            'model': StoneCut,
            'label': 'Tailles de pierres',
            'singular': 'Taille',
            'fields': ['code', 'name', 'rank', 'is_active'],
            'list_display': ['code', 'name', 'rank', 'is_active'],
            'search_fields': ['code', 'name'],
        },
        'payment-methods': {
            'model': PaymentMethod,
            'label': 'Modes de paiement',
            'singular': 'Mode de paiement',
            'fields': ['name', 'code', 'requires_reference', 'requires_bank_account', 'is_active', 'display_order'],
            'list_display': ['name', 'code', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'bank-accounts': {
            'model': BankAccount,
            'label': 'Comptes bancaires',
            'singular': 'Compte bancaire',
            'fields': ['bank_name', 'account_name', 'account_number', 'rib', 'swift', 'is_active', 'is_default', 'notes'],
            'list_display': ['bank_name', 'account_name', 'is_active', 'is_default'],
            'search_fields': ['bank_name', 'account_name', 'rib'],
        },
        'stock-locations': {
            'model': StockLocation,
            'label': 'Emplacements de stock',
            'singular': 'Emplacement',
            'fields': ['name', 'code', 'description', 'is_secure', 'is_active'],
            'list_display': ['name', 'code', 'is_secure', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'delivery-methods': {
            'model': DeliveryMethod,
            'label': 'Modes de livraison',
            'singular': 'Mode de livraison',
            'fields': ['name', 'code', 'is_internal', 'default_cost', 'is_active'],
            'list_display': ['name', 'code', 'is_internal', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'delivery-persons': {
            'model': DeliveryPerson,
            'label': 'Livreurs',
            'singular': 'Livreur',
            'fields': ['name', 'phone', 'is_active', 'notes'],
            'list_display': ['name', 'phone', 'is_active'],
            'search_fields': ['name', 'phone'],
        },
        'repair-types': {
            'model': RepairType,
            'label': 'Types de réparations',
            'singular': 'Type de réparation',
            'fields': ['name', 'code', 'default_price', 'estimated_duration_days', 'is_active'],
            'list_display': ['name', 'code', 'default_price', 'is_active'],
            'search_fields': ['name', 'code'],
        },
        'certificate-issuers': {
            'model': CertificateIssuer,
            'label': 'Émetteurs de certificats',
            'singular': 'Émetteur',
            'fields': ['name', 'code', 'website', 'is_active'],
            'list_display': ['name', 'code', 'is_active'],
            'search_fields': ['name', 'code'],
        },
    }

    @classmethod
    def get_model(cls, config_type):
        """Get model class for a configuration type"""
        if config_type not in cls.MODELS:
            raise Http404(f"Configuration type '{config_type}' not found")
        return cls.MODELS[config_type]['model']

    @classmethod
    def get_config(cls, config_type):
        """Get full configuration for a model type"""
        if config_type not in cls.MODELS:
            raise Http404(f"Configuration type '{config_type}' not found")
        return cls.MODELS[config_type]

    @classmethod
    def get_all_configs(cls):
        """Get statistics for all configuration types"""
        configs = {}
        for key, config in cls.MODELS.items():
            model = config['model']
            configs[key] = {
                **config,
                'count': model.objects.count(),
            }
        return configs


def generate_model_form(model, fields):
    """
    Dynamically generate a ModelForm for a given model with proper styling.
    Uses proper Django widget instances instead of dictionaries.
    """
    from django import forms

    base_attrs = {
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500',
    }

    widgets = {}
    for field_name in fields:
        try:
            field = model._meta.get_field(field_name)

            # Boolean/Checkbox fields
            if field_name in ['is_active', 'is_default', 'is_precious', 'requires_certificate',
                             'requires_reference', 'requires_bank_account', 'is_internal', 'is_secure']:
                widgets[field_name] = forms.CheckboxInput(attrs={'class': 'w-4 h-4 rounded'})

            # Choice fields (Select dropdowns)
            elif hasattr(field, 'choices') and field.choices:
                widgets[field_name] = forms.Select(attrs=base_attrs)

            # DateTime fields
            elif field.get_internal_type() == 'DateTimeField':
                widgets[field_name] = forms.DateTimeInput(
                    attrs={**base_attrs, 'type': 'datetime-local'},
                    format='%Y-%m-%dT%H:%M'
                )

            # Date fields
            elif field.get_internal_type() == 'DateField':
                widgets[field_name] = forms.DateInput(
                    attrs={**base_attrs, 'type': 'date'},
                    format='%Y-%m-%d'
                )

            # Integer fields
            elif field.get_internal_type() == 'IntegerField':
                widgets[field_name] = forms.NumberInput(attrs={**base_attrs, 'type': 'number'})

            # Decimal/Float fields
            elif field.get_internal_type() == 'DecimalField':
                widgets[field_name] = forms.NumberInput(
                    attrs={**base_attrs, 'type': 'number', 'step': '0.01'}
                )

            # Text areas (large text)
            elif field.get_internal_type() == 'TextField':
                widgets[field_name] = forms.Textarea(
                    attrs={**base_attrs, 'rows': '3'}
                )

            # Default: Text input
            else:
                widgets[field_name] = forms.TextInput(attrs=base_attrs)

        except Exception:
            # Fallback to TextInput for any unhandled field types
            widgets[field_name] = forms.TextInput(attrs=base_attrs)

    class_name = f'{model.__name__}DynamicForm'
    return type(class_name, (ModelForm,), {
        'Meta': type('Meta', (), {
            'model': model,
            'fields': fields,
            'widgets': widgets
        })
    })


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
    """System Configuration - Manage all system settings

    Displays statistics and management options for all 15 configuration types.
    Uses the ConfigurationRegistry for comprehensive coverage.
    """

    # Get all configuration types with counts
    all_configs = ConfigurationRegistry.get_all_configs()

    # Add querysets to each config for template iteration
    for config_key, config in all_configs.items():
        config['items'] = config['model'].objects.all()

    context = {
        'page_title': 'Configuration Système',
        'section': 'configuration',
        'all_configs': all_configs,

        # Legacy counts for backward compatibility with template
        'metal_types_count': all_configs.get('metal-types', {}).get('count', 0),
        'metal_purities_count': all_configs.get('metal-purities', {}).get('count', 0),
        'product_categories_count': all_configs.get('categories', {}).get('count', 0),
        'stone_types_count': all_configs.get('stone-types', {}).get('count', 0),
        'stone_clarities_count': all_configs.get('stone-clarities', {}).get('count', 0),
        'stone_colors_count': all_configs.get('stone-colors', {}).get('count', 0),
        'stone_cuts_count': all_configs.get('stone-cuts', {}).get('count', 0),
        'payment_methods_count': all_configs.get('payment-methods', {}).get('count', 0),
        'bank_accounts_count': all_configs.get('bank-accounts', {}).get('count', 0),
        'stock_locations_count': all_configs.get('stock-locations', {}).get('count', 0),
        'delivery_methods_count': all_configs.get('delivery-methods', {}).get('count', 0),
        'delivery_persons_count': all_configs.get('delivery-persons', {}).get('count', 0),
        'repair_types_count': all_configs.get('repair-types', {}).get('count', 0),
        'certificate_issuers_count': all_configs.get('certificate-issuers', {}).get('count', 0),
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


# ============================================================================
# GENERIC CONFIGURATION CRUD VIEWS - DRY Implementation
# ============================================================================
# These generic views handle CREATE, EDIT, and DELETE for all 15+ configuration
# model types through dynamic model resolution via ConfigurationRegistry.
# This eliminates code duplication and provides consistent behavior across types.

class ConfigurationCreateView(CreateView):
    """
    Generic CREATE view for all configuration models.
    URL parameter 'config_type' determines which model to use.
    """
    template_name = 'admin_dashboard/config/generic_form.html'
    success_url = reverse_lazy('admin_dashboard:configuration')

    def dispatch(self, request, *args, **kwargs):
        # Check authentication and staff status
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, 'Accès non autorisé.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_config_type(self):
        return self.kwargs.get('config_type')

    def get_model(self):
        return ConfigurationRegistry.get_model(self.get_config_type())

    def get_form_class(self):
        config = ConfigurationRegistry.get_config(self.get_config_type())
        return generate_model_form(config['model'], config['fields'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = ConfigurationRegistry.get_config(self.get_config_type())
        context['is_create'] = True
        context['config_type'] = self.get_config_type()
        context['page_title'] = f'Créer {config["singular"]}'
        context['section'] = 'configuration'
        context['config'] = config
        return context

    def form_valid(self, form):
        config = ConfigurationRegistry.get_config(self.get_config_type())
        response = super().form_valid(form)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            action='create',
            model_name=config['model'].__name__,
            object_id=self.object.id,
            description=f'Créé {config["singular"]}: {self.object}',
            ip_address=get_client_ip(self.request),
        )

        obj_str = str(self.object)
        messages.success(
            self.request,
            f'{config["singular"]} "{obj_str}" créé avec succès.'
        )
        return response


class ConfigurationUpdateView(UpdateView):
    """
    Generic UPDATE view for all configuration models.
    URL parameter 'config_type' determines which model to use.
    """
    template_name = 'admin_dashboard/config/generic_form.html'
    success_url = reverse_lazy('admin_dashboard:configuration')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, 'Accès non autorisé.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_config_type(self):
        return self.kwargs.get('config_type')

    def get_model(self):
        return ConfigurationRegistry.get_model(self.get_config_type())

    def get_form_class(self):
        config = ConfigurationRegistry.get_config(self.get_config_type())
        return generate_model_form(config['model'], config['fields'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = ConfigurationRegistry.get_config(self.get_config_type())
        context['is_create'] = False
        context['config_type'] = self.get_config_type()
        context['page_title'] = f'Éditer {config["singular"]}'
        context['section'] = 'configuration'
        context['config'] = config
        return context

    def form_valid(self, form):
        config = ConfigurationRegistry.get_config(self.get_config_type())
        response = super().form_valid(form)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            action='update',
            model_name=config['model'].__name__,
            object_id=self.object.id,
            description=f'Modifié {config["singular"]}: {self.object}',
            ip_address=get_client_ip(self.request),
        )

        obj_str = str(self.object)
        messages.success(
            self.request,
            f'{config["singular"]} "{obj_str}" mis à jour.'
        )
        return response


class ConfigurationDeleteView(DeleteView):
    """
    Generic DELETE view for all configuration models.
    URL parameter 'config_type' determines which model to use.
    Requires POST method for safety.
    """
    success_url = reverse_lazy('admin_dashboard:configuration')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, 'Accès non autorisé.')
            return redirect('dashboard')
        if request.method != 'POST':
            return redirect('admin_dashboard:configuration')
        return super().dispatch(request, *args, **kwargs)

    def get_config_type(self):
        return self.kwargs.get('config_type')

    def get_model(self):
        return ConfigurationRegistry.get_model(self.get_config_type())

    def get_object(self, queryset=None):
        model = self.get_model()
        pk = self.kwargs.get('pk')
        return get_object_or_404(model, pk=pk)

    def delete(self, request, *args, **kwargs):
        config = ConfigurationRegistry.get_config(self.get_config_type())
        obj_str = str(self.get_object())

        # Log activity before deletion
        ActivityLog.objects.create(
            user=request.user,
            action='delete',
            model_name=config['model'].__name__,
            description=f'Supprimé {config["singular"]}: {obj_str}',
            ip_address=get_client_ip(request),
        )

        response = super().delete(request, *args, **kwargs)
        messages.success(
            request,
            f'{config["singular"]} "{obj_str}" supprimé.'
        )
        return response


# Keep backward compatibility with old URL patterns by delegating to new views
@login_required(login_url='login')
@staff_required
def metal_type_create(request):
    """Backward compatibility wrapper"""
    view = ConfigurationCreateView.as_view()
    view.kwargs = {'config_type': 'metal-types'}
    return view(request, config_type='metal-types')


@login_required(login_url='login')
@staff_required
def metal_type_edit(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationUpdateView.as_view()
    return view(request, config_type='metal-types', pk=pk)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def metal_type_delete(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationDeleteView.as_view()
    return view(request, config_type='metal-types', pk=pk)


@login_required(login_url='login')
@staff_required
def payment_method_create(request):
    """Backward compatibility wrapper"""
    view = ConfigurationCreateView.as_view()
    return view(request, config_type='payment-methods')


@login_required(login_url='login')
@staff_required
def payment_method_edit(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationUpdateView.as_view()
    return view(request, config_type='payment-methods', pk=pk)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def payment_method_delete(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationDeleteView.as_view()
    return view(request, config_type='payment-methods', pk=pk)


@login_required(login_url='login')
@staff_required
def product_category_create(request):
    """Backward compatibility wrapper"""
    view = ConfigurationCreateView.as_view()
    return view(request, config_type='categories')


@login_required(login_url='login')
@staff_required
def product_category_edit(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationUpdateView.as_view()
    return view(request, config_type='categories', pk=pk)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def product_category_delete(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationDeleteView.as_view()
    return view(request, config_type='categories', pk=pk)


@login_required(login_url='login')
@staff_required
def bank_account_create(request):
    """Backward compatibility wrapper"""
    view = ConfigurationCreateView.as_view()
    return view(request, config_type='bank-accounts')


@login_required(login_url='login')
@staff_required
def bank_account_edit(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationUpdateView.as_view()
    return view(request, config_type='bank-accounts', pk=pk)


@login_required(login_url='login')
@staff_required
@require_http_methods(["POST"])
def bank_account_delete(request, pk):
    """Backward compatibility wrapper"""
    view = ConfigurationDeleteView.as_view()
    return view(request, config_type='bank-accounts', pk=pk)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
