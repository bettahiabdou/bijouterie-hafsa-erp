"""
Product management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, F
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from .models import Product, ProductImage, ProductStone
from .print_utils import print_product_label, print_price_tag, print_test_label
from settings_app.models import ProductCategory, MetalType, MetalPurity, BankAccount
from suppliers.models import Supplier
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
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Truly common parameters (only pricing and margins are common)
            purchase_price_per_gram = float(request.POST.get('purchase_price_per_gram', 0))
            labor_cost = float(request.POST.get('labor_cost', 0))
            stone_cost = float(request.POST.get('stone_cost', 0))
            other_cost = float(request.POST.get('other_cost', 0))

            # Margin settings
            margin_type = request.POST.get('margin_type', 'percentage')
            margin_value = float(request.POST.get('margin_value', 25))

            # Product data - Extract all product fields (including per-product fields)
            product_names = request.POST.getlist('product_name')
            product_categories = request.POST.getlist('product_category')
            product_types = request.POST.getlist('product_type')
            product_metals = request.POST.getlist('product_metal_type')
            product_purities = request.POST.getlist('product_purity')
            product_weights_net = request.POST.getlist('product_weight')
            product_weights_gross = request.POST.getlist('product_gross_weight')
            product_selling_prices = request.POST.getlist('product_selling_price')
            product_banks = request.POST.getlist('product_bank_account')
            product_suppliers = request.POST.getlist('product_supplier')

            # Check if we should print labels
            print_labels = request.POST.get('print_labels') == '1'

            created_count = 0
            failed_rows = []
            created_products = []  # Keep track of created products for printing

            for i, weight_net_str in enumerate(product_weights_net):
                try:
                    # Parse weights
                    weight_net = float(weight_net_str) if weight_net_str else 0
                    weight_gross = float(product_weights_gross[i]) if i < len(product_weights_gross) and product_weights_gross[i] else weight_net

                    # Skip empty rows
                    if weight_net <= 0:
                        continue

                    # Get product name (with default fallback)
                    product_name = product_names[i].strip() if i < len(product_names) else ""
                    if not product_name:
                        product_name = f"Produit {created_count + 1}"

                    # Get selling price override if user entered it
                    selling_price_override = None
                    if i < len(product_selling_prices) and product_selling_prices[i].strip():
                        try:
                            selling_price_override = float(product_selling_prices[i])
                        except ValueError:
                            pass

                    # Get per-product fields
                    product_category_id = product_categories[i] if i < len(product_categories) else None
                    product_product_type = product_types[i] if i < len(product_types) else 'finished'
                    product_metal_id = product_metals[i] if i < len(product_metals) else None
                    product_purity_id = product_purities[i] if i < len(product_purities) else None
                    product_bank_id = product_banks[i] if i < len(product_banks) else None
                    product_supplier_id = product_suppliers[i] if i < len(product_suppliers) else None

                    # Create product instance (don't save yet)
                    product = Product(
                        name=product_name,
                        product_type=product_product_type,
                        category_id=product_category_id,
                        metal_type_id=product_metal_id if product_metal_id else None,
                        metal_purity_id=product_purity_id if product_purity_id else None,
                        net_weight=weight_net,
                        gross_weight=weight_gross,
                        purchase_price_per_gram=purchase_price_per_gram,
                        labor_cost=labor_cost,
                        stone_cost=stone_cost,
                        other_cost=other_cost,
                        margin_type=margin_type,
                        margin_value=margin_value,
                        bank_account_id=product_bank_id if product_bank_id else None,
                        supplier_id=product_supplier_id if product_supplier_id else None,
                        status='available',
                        created_by=request.user,
                    )
                    # Save product - triggers auto-generation and calculations
                    product.save()

                    # If user provided a selling price override, update it
                    if selling_price_override is not None:
                        product.selling_price = selling_price_override
                        product.save(update_fields=['selling_price'])

                    # Handle image upload for this product (if any)
                    product_images = request.FILES.getlist(f'product_image_{i}')
                    for idx, img_file in enumerate(product_images):
                        img_file.seek(0)
                        prod_image = ProductImage.objects.create(
                            product=product,
                            image=img_file,
                            is_primary=(idx == 0),
                            display_order=idx
                        )
                        # Set first image as main_image (use the saved ProductImage path)
                        if idx == 0:
                            product.main_image = prod_image.image
                            product.save(update_fields=['main_image'])

                    # Log activity
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.CREATE,
                        model_name='Product',
                        object_id=str(product.id),
                        object_repr=product.reference,
                        ip_address=get_client_ip(request)
                    )

                    created_products.append(product)
                    created_count += 1

                except (ValueError, TypeError) as e:
                    failed_rows.append((i + 1, str(e)))
                    logger.warning(f'Failed to create batch product at row {i + 1}: {str(e)}')
                    continue
                except Exception as e:
                    failed_rows.append((i + 1, str(e)))
                    logger.exception(f'Unexpected error creating batch product at row {i + 1}')
                    continue

            # Provide success/warning feedback
            if created_count > 0:
                messages.success(request, f'{created_count} produit(s) créé(s) avec succès.')

            if failed_rows:
                error_details = '; '.join([f"Ligne {row}: {error}" for row, error in failed_rows])
                messages.warning(request, f'Certaines lignes n\'ont pas pu être créées: {error_details}')

            # Print labels if requested
            if print_labels and created_products:
                printed_count = 0
                print_errors = []
                for product in created_products:
                    try:
                        success, msg = print_product_label(product, 1)
                        if success:
                            printed_count += 1
                            # Log print activity
                            ActivityLog.objects.create(
                                user=request.user,
                                action=ActivityLog.ActionType.PRINT,
                                model_name='Product',
                                object_id=str(product.id),
                                object_repr=f"{product.reference} - batch print",
                                ip_address=get_client_ip(request)
                            )
                        else:
                            print_errors.append(f"{product.reference}: {msg}")
                    except Exception as e:
                        print_errors.append(f"{product.reference}: {str(e)}")

                if printed_count > 0:
                    messages.info(request, f'{printed_count} étiquette(s) envoyée(s) à l\'imprimante.')
                if print_errors:
                    messages.warning(request, f'Erreurs d\'impression: {"; ".join(print_errors[:3])}')

            return redirect('products:list')

        except Exception as e:
            logger.exception(f'Error in batch product creation: {str(e)}')
            messages.error(request, f'Erreur lors de la création en lot: {str(e)}')

    context = {
        'categories': ProductCategory.objects.all(),
        'metals': MetalType.objects.filter(is_active=True),
        'purities': MetalPurity.objects.filter(is_active=True),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
        'suppliers': Supplier.objects.filter(is_active=True),
        'product_types': Product.ProductType.choices,
    }

    return render(request, 'products/batch_product_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def product_create(request):
    """Create a new product"""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'ajouter des produits.')
        return redirect('products:list')

    if request.method == 'POST':
        try:
            import logging
            logger = logging.getLogger(__name__)

            bank_account_id = request.POST.get('bank_account')

            # Convert string form inputs to proper types
            try:
                gross_weight = float(request.POST.get('gross_weight', 0) or 0)
                net_weight = float(request.POST.get('net_weight', 0) or 0)
                purchase_price_per_gram = float(request.POST.get('purchase_price_per_gram', 0) or 0)
                minimum_price = float(request.POST.get('minimum_price', 0) or 0)
                labor_cost = float(request.POST.get('labor_cost', 0) or 0)
                stone_cost = float(request.POST.get('stone_cost', 0) or 0)
                other_cost = float(request.POST.get('other_cost', 0) or 0)
                margin_value = float(request.POST.get('margin_value', 25) or 25)
            except (ValueError, TypeError) as e:
                messages.error(request, f'Erreur dans les valeurs numériques: {str(e)}')
                return render(request, 'products/product_form.html', {
                    'categories': ProductCategory.objects.all(),
                    'metals': MetalType.objects.filter(is_active=True),
                    'purities': MetalPurity.objects.filter(is_active=True),
                    'bank_accounts': BankAccount.objects.filter(is_active=True),
                    'product_types': Product.ProductType.choices,
                })

            # Create product instance (don't save yet)
            product = Product(
                name=request.POST.get('name'),
                name_ar=request.POST.get('name_ar', ''),
                description=request.POST.get('description', ''),
                product_type=request.POST.get('product_type', 'finished'),
                category_id=request.POST.get('category'),
                metal_type_id=request.POST.get('metal_type') or None,
                metal_purity_id=request.POST.get('metal_purity') or None,
                gross_weight=gross_weight,
                net_weight=net_weight,
                purchase_price_per_gram=purchase_price_per_gram,
                minimum_price=minimum_price,
                labor_cost=labor_cost,
                stone_cost=stone_cost,
                other_cost=other_cost,
                margin_type=request.POST.get('margin_type', 'percentage'),
                margin_value=margin_value,
                bank_account_id=bank_account_id if bank_account_id else None,
                status='available',
                created_by=request.user,
            )

            # Save product - this triggers auto-generation and calculations in save() method
            product.save()

            # Handle image uploads
            images = request.FILES.getlist('images')
            for i, image_file in enumerate(images):
                # Reset file pointer before each use
                image_file.seek(0)
                product_image = ProductImage.objects.create(
                    product=product,
                    image=image_file,
                    is_primary=(i == 0),
                    display_order=i
                )
                # Set first image as main_image (use the saved ProductImage path)
                if i == 0:
                    product.main_image = product_image.image
                    product.save(update_fields=['main_image'])

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
            return redirect('products:detail', reference=product.reference)

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
        return redirect('products:detail', reference=reference)

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

            # Handle image deletions
            delete_main_image = request.POST.get('delete_main_image')
            if delete_main_image and product.main_image:
                product.main_image.delete(save=False)
                product.main_image = None
                product.save(update_fields=['main_image'])

            delete_image_ids = request.POST.getlist('delete_images')
            if delete_image_ids:
                ProductImage.objects.filter(id__in=delete_image_ids, product=product).delete()

            # Handle new image uploads
            images = request.FILES.getlist('images')
            existing_count = product.images.count()
            for i, image_file in enumerate(images):
                image_file.seek(0)
                product_image = ProductImage.objects.create(
                    product=product,
                    image=image_file,
                    is_primary=False,
                    display_order=existing_count + i
                )
                # Set as main_image if none exists (use the saved ProductImage path)
                if i == 0 and not product.main_image:
                    product.main_image = product_image.image
                    product.save(update_fields=['main_image'])

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
            return redirect('products:detail', reference=product.reference)

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


@login_required(login_url='login')
@require_http_methods(["POST"])
def print_label(request, reference):
    """Print a product label"""
    product = get_object_or_404(Product, reference=reference)

    label_type = request.POST.get('label_type', 'product')
    quantity = int(request.POST.get('quantity', 1))

    if quantity < 1 or quantity > 10:
        quantity = 1

    if label_type == 'price':
        success, message = print_price_tag(product, quantity)
    else:
        success, message = print_product_label(product, quantity)

    # Log activity
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.PRINT,
        model_name='Product',
        object_id=str(product.id),
        object_repr=f"{product.reference} - {label_type} x{quantity}",
        ip_address=get_client_ip(request)
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': success, 'message': message})

    if success:
        messages.success(request, f'Étiquette imprimée pour {product.reference}')
    else:
        messages.error(request, f'Erreur d\'impression: {message}')

    return redirect('products:detail', reference=reference)


@login_required(login_url='login')
@require_http_methods(["POST"])
def print_test(request):
    """Print a test label"""
    success, message = print_test_label()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': success, 'message': message})

    if success:
        messages.success(request, 'Test d\'impression réussi!')
    else:
        messages.error(request, f'Erreur d\'impression: {message}')

    return redirect('products:list')
