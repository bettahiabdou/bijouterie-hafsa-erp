"""
Product management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, F
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from .models import Product, ProductImage, ProductStone
from settings_app.models import ProductCategory, MetalType, MetalPurity, BankAccount
from users.models import ActivityLog


@login_required(login_url='login')
def product_list(request):
    """List all products with filtering and search"""
    products = Product.objects.select_related(
        'category', 'metal_type', 'metal_purity'
    ).prefetch_related('images')

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(reference__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(name_ar__icontains=search_query) |
            Q(barcode__icontains=search_query)
        )

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        products = products.filter(status=status_filter)

    # Filter by category
    category_filter = request.GET.get('category', '')
    if category_filter:
        products = products.filter(category_id=category_filter)

    # Filter by metal type
    metal_filter = request.GET.get('metal', '')
    if metal_filter:
        products = products.filter(metal_type_id=metal_filter)

    # Sort
    sort_by = request.GET.get('sort', '-created_at')
    try:
        products = products.order_by(sort_by)
    except:
        products = products.order_by('-created_at')

    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Statistics
    stats = {
        'total': Product.objects.count(),
        'available': Product.objects.filter(status='available').count(),
        'sold': Product.objects.filter(status='sold').count(),
        'in_repair': Product.objects.filter(status='in_repair').count(),
    }

    context = {
        'page_obj': page_obj,
        'products': page_obj.object_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'metal_filter': metal_filter,
        'sort_by': sort_by,
        'categories': ProductCategory.objects.all(),
        'metals': MetalType.objects.filter(is_active=True),
        'stats': stats,
        'statuses': Product.Status.choices,
    }

    return render(request, 'products/product_list.html', context)


@login_required(login_url='login')
def product_detail(request, reference):
    """Display product details"""
    product = get_object_or_404(
        Product.objects.select_related(
            'category', 'metal_type', 'metal_purity'
        ).prefetch_related('images', 'stones'),
        reference=reference
    )

    # Log view activity
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.VIEW,
        model_name='Product',
        object_id=str(product.id),
        object_repr=product.reference,
        ip_address=get_client_ip(request)
    )

    context = {
        'product': product,
        'images': product.images.all(),
        'stones': product.stones.all(),
    }

    return render(request, 'products/product_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def batch_product_create(request):
    """Create multiple products at once with shared parameters"""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'ajouter des produits.')
        return redirect('products:list')

    if request.method == 'POST':
        try:
            # Common parameters
            category_id = request.POST.get('category')
            product_type = request.POST.get('product_type', 'finished')
            metal_type_id = request.POST.get('metal_type')
            metal_purity_id = request.POST.get('metal_purity')
            bank_account_id = request.POST.get('bank_account')

            # Unit pricing
            purchase_price_per_gram = float(request.POST.get('purchase_price_per_gram', 0))
            labor_cost = float(request.POST.get('labor_cost', 0))
            stone_cost = float(request.POST.get('stone_cost', 0))
            other_cost = float(request.POST.get('other_cost', 0))

            # Margin settings
            margin_type = request.POST.get('margin_type', 'percentage')
            margin_value = float(request.POST.get('margin_value', 25))

            # Product data
            product_weights = request.POST.getlist('product_weight')
            product_selling_prices = request.POST.getlist('product_selling_price')

            created_count = 0
            for i, weight_str in enumerate(product_weights):
                try:
                    weight = float(weight_str)
                    if weight <= 0:
                        continue

                    selling_price = float(product_selling_prices[i]) if i < len(product_selling_prices) else 0

                    # Create product instance (don't save yet)
                    product = Product(
                        name=f"Produit Lot {i+1}",
                        product_type=product_type,
                        category_id=category_id,
                        metal_type_id=metal_type_id if metal_type_id else None,
                        metal_purity_id=metal_purity_id if metal_purity_id else None,
                        net_weight=weight,
                        gross_weight=weight,
                        purchase_price_per_gram=purchase_price_per_gram,
                        labor_cost=labor_cost,
                        stone_cost=stone_cost,
                        other_cost=other_cost,
                        margin_type=margin_type,
                        margin_value=margin_value,
                        bank_account_id=bank_account_id if bank_account_id else None,
                        status='available',
                        created_by=request.user,
                    )
                    # Save product - triggers auto-generation and calculations
                    product.save()

                    # Log activity
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.CREATE,
                        model_name='Product',
                        object_id=str(product.id),
                        object_repr=product.reference,
                        ip_address=get_client_ip(request)
                    )

                    created_count += 1

                except (ValueError, TypeError):
                    continue

            messages.success(request, f'{created_count} produit(s) créé(s) avec succès.')
            return redirect('products:list')

        except Exception as e:
            messages.error(request, f'Erreur lors de la création en lot: {str(e)}')

    context = {
        'categories': ProductCategory.objects.all(),
        'metals': MetalType.objects.filter(is_active=True),
        'purities': MetalPurity.objects.filter(is_active=True),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
        'product_types': Product.ProductType.choices,
    }

    return render(request, 'products/batch_product_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def product_create(request):
    """Create a new product"""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'ajouter des produits.')
        return redirect('product_list')

    if request.method == 'POST':
        try:
            import logging
            logger = logging.getLogger(__name__)

            bank_account_id = request.POST.get('bank_account')

            # Create product instance (don't save yet)
            product = Product(
                name=request.POST.get('name'),
                name_ar=request.POST.get('name_ar', ''),
                description=request.POST.get('description', ''),
                product_type=request.POST.get('product_type', 'finished'),
                category_id=request.POST.get('category'),
                metal_type_id=request.POST.get('metal_type') or None,
                metal_purity_id=request.POST.get('metal_purity') or None,
                gross_weight=request.POST.get('gross_weight', 0) or 0,
                net_weight=request.POST.get('net_weight', 0) or 0,
                purchase_price_per_gram=request.POST.get('purchase_price_per_gram', 0) or 0,
                minimum_price=request.POST.get('minimum_price', 0) or 0,
                labor_cost=request.POST.get('labor_cost', 0) or 0,
                stone_cost=request.POST.get('stone_cost', 0) or 0,
                other_cost=request.POST.get('other_cost', 0) or 0,
                margin_type=request.POST.get('margin_type', 'percentage'),
                margin_value=request.POST.get('margin_value', 25) or 25,
                bank_account_id=bank_account_id if bank_account_id else None,
                status='available',
                created_by=request.user,
            )

            # Save product - this triggers auto-generation and calculations in save() method
            product.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.CREATE,
                model_name='Product',
                object_id=str(product.id),
                object_repr=product.reference,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Produit "{product.name}" créé avec succès.')
            return redirect('product_detail', reference=product.reference)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error creating product: {str(e)}')
            messages.error(request, f'Erreur lors de la création: {str(e)}')

    context = {
        'categories': ProductCategory.objects.all(),
        'metals': MetalType.objects.filter(is_active=True),
        'purities': MetalPurity.objects.filter(is_active=True),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
        'product_types': Product.ProductType.choices,
    }

    return render(request, 'products/product_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def product_edit(request, reference):
    """Edit an existing product"""
    product = get_object_or_404(Product, reference=reference)

    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de modifier les produits.')
        return redirect('product_detail', reference=reference)

    if request.method == 'POST':
        try:
            product.name = request.POST.get('name', product.name)
            product.name_ar = request.POST.get('name_ar', product.name_ar)
            product.description = request.POST.get('description', product.description)
            product.gross_weight = request.POST.get('gross_weight', product.gross_weight)
            product.net_weight = request.POST.get('net_weight', product.net_weight)
            product.purchase_price_per_gram = request.POST.get('purchase_price_per_gram', product.purchase_price_per_gram)
            product.minimum_price = request.POST.get('minimum_price', product.minimum_price)
            product.labor_cost = request.POST.get('labor_cost', product.labor_cost)
            product.stone_cost = request.POST.get('stone_cost', product.stone_cost)
            product.other_cost = request.POST.get('other_cost', product.other_cost)
            product.margin_type = request.POST.get('margin_type', product.margin_type)
            product.margin_value = request.POST.get('margin_value', product.margin_value)
            product.status = request.POST.get('status', product.status)

            if request.POST.get('metal_type'):
                product.metal_type_id = request.POST.get('metal_type')
            if request.POST.get('metal_purity'):
                product.metal_purity_id = request.POST.get('metal_purity')
            if request.POST.get('bank_account'):
                product.bank_account_id = request.POST.get('bank_account')

            product.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.UPDATE,
                model_name='Product',
                object_id=str(product.id),
                object_repr=product.reference,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Produit "{product.name}" modifié avec succès.')
            return redirect('product_detail', reference=product.reference)

        except Exception as e:
            messages.error(request, f'Erreur lors de la modification: {str(e)}')

    context = {
        'product': product,
        'categories': ProductCategory.objects.all(),
        'metals': MetalType.objects.filter(is_active=True),
        'purities': MetalPurity.objects.filter(is_active=True),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
        'product_types': Product.ProductType.choices,
        'statuses': Product.Status.choices,
    }

    return render(request, 'products/product_form.html', context)


@login_required(login_url='login')
def inventory_dashboard(request):
    """Display inventory statistics and alerts"""
    if not request.user.is_staff and not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas accès à ce tableau de bord.')
        return redirect('dashboard')

    # Overall statistics
    total_products = Product.objects.count()
    available_products = Product.objects.filter(status='available').count()
    sold_products = Product.objects.filter(status='sold').count()
    in_repair_products = Product.objects.filter(status='in_repair').count()

    # Value calculations
    total_value = Product.objects.aggregate(
        total=Sum(F('selling_price'))
    )['total'] or 0

    # Status breakdown
    status_breakdown = Product.objects.values('status').annotate(count=Count('id')).order_by('status')

    # Metal breakdown
    metal_breakdown = Product.objects.values('metal_type__name').annotate(
        count=Count('id'),
        total_weight=Sum('gross_weight')
    ).order_by('-count')[:10]

    # Low stock items (minimum price below selling price indicates low stock)
    low_stock_items = Product.objects.filter(
        status='available'
    ).order_by('gross_weight')[:20]

    context = {
        'total_products': total_products,
        'available_products': available_products,
        'sold_products': sold_products,
        'in_repair_products': in_repair_products,
        'total_value': total_value,
        'status_breakdown': list(status_breakdown),
        'metal_breakdown': list(metal_breakdown),
        'low_stock_items': low_stock_items,
    }

    return render(request, 'products/inventory_dashboard.html', context)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
