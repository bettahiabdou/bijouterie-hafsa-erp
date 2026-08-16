"""
Product management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from decimal import Decimal, InvalidOperation
import csv
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import Product, ProductImage, ProductStone, ProductVideo, StockCountSession, StockCountScan, ProductBlock
from .video_utils import convert_video_to_mp4
from .print_utils import print_product_label, print_price_tag, print_test_label, generate_product_label_zpl, generate_price_tag_zpl, queue_print_job, send_to_printer
from settings_app.models import ProductCategory, MetalType, MetalPurity, BankAccount, JewelryType, ProductNature
from suppliers.models import Supplier
from users.models import ActivityLog
from PIL import Image
from io import BytesIO
import os


def convert_image_to_jpeg(image_file):
    """
    Convert uploaded image to JPEG format if it's HEIC or other non-web formats.
    Also handles EXIF orientation to fix rotated iPhone photos.
    Returns a new InMemoryUploadedFile with the converted image.
    """
    from PIL import ExifTags

    filename = image_file.name.lower()

    # Check if it's a HEIC file or other format that needs conversion
    if filename.endswith(('.heic', '.heif')):
        try:
            # Try to use pillow-heif for HEIC support
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            # If pillow-heif not installed, try anyway with PIL
            pass

    try:
        # Reset file pointer
        image_file.seek(0)

        # Open image with PIL
        img = Image.open(image_file)

        # Fix EXIF orientation (iPhone photos are often rotated)
        try:
            # Find the orientation tag
            orientation_key = None
            for key in ExifTags.TAGS.keys():
                if ExifTags.TAGS[key] == 'Orientation':
                    orientation_key = key
                    break

            if orientation_key and hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                if exif and orientation_key in exif:
                    orientation = exif[orientation_key]

                    # Apply rotation based on EXIF orientation value
                    if orientation == 2:
                        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    elif orientation == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation == 4:
                        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    elif orientation == 5:
                        img = img.rotate(-90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    elif orientation == 6:
                        img = img.rotate(-90, expand=True)
                    elif orientation == 7:
                        img = img.rotate(90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    elif orientation == 8:
                        img = img.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError, TypeError):
            # If EXIF reading fails, continue without rotation
            pass

        # Convert to RGB if necessary (for RGBA, P mode images)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparency
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if too large (max 2000px on longest side)
        max_size = 2000
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Save to BytesIO as JPEG
        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        # Create new filename with .jpg extension
        base_name = os.path.splitext(image_file.name)[0]
        new_filename = f"{base_name}.jpg"

        # Return new InMemoryUploadedFile
        return InMemoryUploadedFile(
            file=output,
            field_name=image_file.field_name if hasattr(image_file, 'field_name') else 'image',
            name=new_filename,
            content_type='image/jpeg',
            size=output.getbuffer().nbytes,
            charset=None
        )
    except Exception as e:
        # If conversion fails, return original file
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Image conversion failed for {image_file.name}: {str(e)}")
        image_file.seek(0)
        return image_file


@login_required(login_url='login')
def product_list(request):
    """List all products with filtering and search"""
    products = Product.objects.select_related(
        'category', 'metal_type', 'metal_purity', 'jewelry_type'
    ).prefetch_related('images')

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(reference__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(name_ar__icontains=search_query) |
            Q(barcode__icontains=search_query) |
            Q(rfid_tag__icontains=search_query)
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

    # Filter by time in stock: only products added more than N days ago
    # (helps surface aged stock to sell fast, or spot pieces that may have
    # left the shop without being declared).
    from django.utils import timezone as _tz
    from datetime import timedelta as _td
    min_age = request.GET.get('min_age', '')
    if min_age:
        try:
            days = int(min_age)
            if days > 0:
                products = products.filter(created_at__lte=_tz.now() - _td(days=days))
        except (ValueError, TypeError):
            pass

    # Sort (whitelisted)
    sort_by = request.GET.get('sort', '-created_at')
    allowed_sorts = {
        '-created_at', 'created_at', 'reference', '-reference',
        'name', '-name', 'selling_price', '-selling_price', 'status',
    }
    if sort_by not in allowed_sorts:
        sort_by = '-created_at'
    products = products.order_by(sort_by)

    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Annotate each product on the page with how long it has been in stock
    _now = _tz.now()
    for _p in page_obj.object_list:
        _p.days_in_stock = (_now - _p.created_at).days if _p.created_at else None

    # Preserve all filters/sort across pagination (everything except page)
    _params = request.GET.copy()
    _params.pop('page', None)
    querystring = _params.urlencode()

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
        'min_age': min_age,
        'sort_by': sort_by,
        'querystring': querystring,
        'categories': ProductCategory.objects.all(),
        'metals': MetalType.objects.filter(is_active=True),
        'stats': stats,
        'statuses': Product.Status.choices,
        'blocks': ProductBlock.objects.filter(is_active=True).order_by('name'),
    }

    return render(request, 'products/product_list.html', context)


@login_required(login_url='login')
def sold_products(request):
    """List sold products (sale line items) with filters: seller, invoice,
    sale-date range, product type, category."""
    from sales.models import SaleInvoiceItem
    from django.contrib.auth import get_user_model
    from django.db.models import Sum as _Sum

    items = SaleInvoiceItem.objects.select_related(
        'product', 'product__category', 'product__metal_type', 'product__metal_purity',
        'invoice', 'invoice__seller', 'invoice__client',
    ).filter(
        invoice__is_deleted=False,
        is_returned=False,
    ).exclude(
        invoice__status__in=['cancelled', 'draft', 'exchanged', 'returned']
    )

    # Search (product ref / name)
    search_query = request.GET.get('search', '')
    if search_query:
        items = items.filter(
            Q(product__reference__icontains=search_query) |
            Q(product__name__icontains=search_query)
        )

    # Seller (of the invoice)
    seller_filter = request.GET.get('seller', '')
    if seller_filter:
        items = items.filter(invoice__seller_id=seller_filter)

    # Linked invoice reference
    invoice_filter = request.GET.get('invoice', '')
    if invoice_filter:
        items = items.filter(invoice__reference__icontains=invoice_filter)

    # Sale date range (invoice date)
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        items = items.filter(invoice__date__gte=date_from)
    if date_to:
        items = items.filter(invoice__date__lte=date_to)

    # Product type
    product_type_filter = request.GET.get('product_type', '')
    if product_type_filter:
        items = items.filter(product__product_type=product_type_filter)

    # Category
    category_filter = request.GET.get('category', '')
    if category_filter:
        items = items.filter(product__category_id=category_filter)

    items = items.order_by('-invoice__date', '-id')

    # Stats over the filtered set
    agg = items.aggregate(
        total_amount=_Sum('total_amount'),
        total_weight=_Sum('product__gross_weight'),
    )

    paginator = Paginator(items, 24)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    from django.contrib.auth import get_user_model
    User = get_user_model()

    context = {
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'search_query': search_query,
        'seller_filter': seller_filter,
        'invoice_filter': invoice_filter,
        'date_from': date_from,
        'date_to': date_to,
        'product_type_filter': product_type_filter,
        'category_filter': category_filter,
        'sellers': User.objects.filter(sales__isnull=False).distinct().order_by('first_name', 'last_name'),
        'categories': ProductCategory.objects.all(),
        'product_types': Product.ProductType.choices,
        'total_count': paginator.count,
        'total_amount': agg['total_amount'] or 0,
        'total_weight': agg['total_weight'] or 0,
    }
    return render(request, 'products/sold_products.html', context)


@login_required(login_url='login')
def product_detail(request, reference):
    """Display product details"""
    product = get_object_or_404(
        Product.objects.select_related(
            'category', 'metal_type', 'metal_purity', 'jewelry_type', 'nature'
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

    # Get linked invoices (sold, reserved, etc.)
    linked_invoices = product.sale_items.select_related(
        'invoice', 'invoice__client', 'invoice__seller'
    ).filter(
        invoice__is_deleted=False
    ).order_by('-invoice__date')

    # Get linked purchase invoice item (facture d'achat)
    linked_purchase_item = product.purchase_items.select_related(
        'invoice', 'invoice__supplier'
    ).first()

    context = {
        'product': product,
        'images': product.images.all(),
        'stones': product.stones.all(),
        'linked_invoices': linked_invoices,
        'linked_purchase_item': linked_purchase_item,
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
            product_sizes = request.POST.getlist('product_size')
            product_jewelry_types = request.POST.getlist('product_jewelry_type')
            product_natures = request.POST.getlist('product_nature')

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
                    product_size = product_sizes[i].strip() if i < len(product_sizes) else ''
                    product_jewelry_type_id = product_jewelry_types[i] if i < len(product_jewelry_types) else None
                    product_nature_id = product_natures[i] if i < len(product_natures) else None

                    # Create product instance (don't save yet)
                    product = Product(
                        name=product_name,
                        product_type=product_product_type,
                        category_id=product_category_id,
                        jewelry_type_id=product_jewelry_type_id if product_jewelry_type_id else None,
                        nature_id=product_nature_id if product_nature_id else None,
                        metal_type_id=product_metal_id if product_metal_id else None,
                        metal_purity_id=product_purity_id if product_purity_id else None,
                        net_weight=weight_net,
                        gross_weight=weight_gross,
                        size=product_size,
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
                        # Convert HEIC/HEIF to JPEG for browser compatibility
                        converted_image = convert_image_to_jpeg(img_file)
                        prod_image = ProductImage.objects.create(
                            product=product,
                            image=converted_image,
                            is_primary=(idx == 0),
                            display_order=idx
                        )
                        # Set first image as main_image (use the saved ProductImage path)
                        if idx == 0:
                            product.main_image = prod_image.image
                            product.save(update_fields=['main_image'])

                    # Set AI image status based on whether images were uploaded
                    if not product_images:
                        product.ai_image_status = Product.AIImageStatus.SKIPPED
                        product.save(update_fields=['ai_image_status'])

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
        'jewelry_types': JewelryType.objects.filter(is_active=True),
        'natures': ProductNature.objects.filter(is_active=True),
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
                    'jewelry_types': JewelryType.objects.filter(is_active=True),
                    'natures': ProductNature.objects.filter(is_active=True),
                })

            # Get size and length
            size = request.POST.get('size', '').strip()
            length = request.POST.get('length', '').strip()
            length_value = float(length) if length else None

            # Create product instance (don't save yet)
            product = Product(
                name=request.POST.get('name'),
                name_ar=request.POST.get('name_ar', ''),
                description=request.POST.get('description', ''),
                product_type=request.POST.get('product_type', 'finished'),
                category_id=request.POST.get('category'),
                jewelry_type_id=request.POST.get('jewelry_type') or None,
                nature_id=request.POST.get('nature') or None,
                metal_type_id=request.POST.get('metal_type') or None,
                metal_purity_id=request.POST.get('metal_purity') or None,
                gross_weight=gross_weight,
                net_weight=net_weight,
                size=size,
                length=length_value,
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
                # Convert HEIC/HEIF to JPEG for browser compatibility
                converted_image = convert_image_to_jpeg(image_file)
                product_image = ProductImage.objects.create(
                    product=product,
                    image=converted_image,
                    is_primary=(i == 0),
                    display_order=i
                )
                # Set first image as main_image (use the saved ProductImage path)
                if i == 0:
                    product.main_image = product_image.image
                    product.save(update_fields=['main_image'])

            # Set AI image status based on whether images were uploaded
            if not images:
                product.ai_image_status = Product.AIImageStatus.SKIPPED
                product.save(update_fields=['ai_image_status'])

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
        'jewelry_types': JewelryType.objects.filter(is_active=True),
        'natures': ProductNature.objects.filter(is_active=True),
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
            # Text fields
            product.name = request.POST.get('name', product.name)
            product.name_ar = request.POST.get('name_ar', product.name_ar)
            product.description = request.POST.get('description', product.description)
            product.product_type = request.POST.get('product_type', product.product_type)
            product.margin_type = request.POST.get('margin_type', product.margin_type)
            product.status = request.POST.get('status', product.status)

            # Size field (text)
            product.size = request.POST.get('size', product.size or '').strip()

            # Numeric fields - convert strings to float
            if request.POST.get('gross_weight'):
                product.gross_weight = float(request.POST.get('gross_weight'))
            if request.POST.get('net_weight'):
                product.net_weight = float(request.POST.get('net_weight'))
            length_str = request.POST.get('length', '').strip()
            if length_str:
                product.length = float(length_str)
            else:
                product.length = None
            if request.POST.get('purchase_price_per_gram'):
                product.purchase_price_per_gram = float(request.POST.get('purchase_price_per_gram'))
            if request.POST.get('minimum_price'):
                product.minimum_price = float(request.POST.get('minimum_price'))
            if request.POST.get('labor_cost'):
                product.labor_cost = float(request.POST.get('labor_cost'))
            if request.POST.get('stone_cost'):
                product.stone_cost = float(request.POST.get('stone_cost'))
            if request.POST.get('other_cost'):
                product.other_cost = float(request.POST.get('other_cost'))
            if request.POST.get('margin_value'):
                product.margin_value = float(request.POST.get('margin_value'))

            # Foreign keys
            if request.POST.get('category'):
                product.category_id = request.POST.get('category')
            if request.POST.get('jewelry_type'):
                product.jewelry_type_id = request.POST.get('jewelry_type')
            else:
                product.jewelry_type_id = None
            if request.POST.get('nature'):
                product.nature_id = request.POST.get('nature')
            else:
                product.nature_id = None
            if request.POST.get('metal_type'):
                product.metal_type_id = request.POST.get('metal_type')
            else:
                product.metal_type_id = None
            if request.POST.get('metal_purity'):
                product.metal_purity_id = request.POST.get('metal_purity')
            else:
                product.metal_purity_id = None
            if request.POST.get('bank_account'):
                product.bank_account_id = request.POST.get('bank_account')
            else:
                product.bank_account_id = None

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
                # Convert HEIC/HEIF to JPEG for browser compatibility
                converted_image = convert_image_to_jpeg(image_file)
                product_image = ProductImage.objects.create(
                    product=product,
                    image=converted_image,
                    is_primary=False,
                    display_order=existing_count + i
                )
                # Set as main_image if none exists (use the saved ProductImage path)
                if i == 0 and not product.main_image:
                    product.main_image = product_image.image
                    product.save(update_fields=['main_image'])

            # If new images were added and the product was previously skipped
            # (no images at creation), reset AI status so cron picks it up
            if images and product.ai_image_status == Product.AIImageStatus.SKIPPED:
                product.ai_image_status = Product.AIImageStatus.PENDING
                product.save(update_fields=['ai_image_status'])

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
        'jewelry_types': JewelryType.objects.filter(is_active=True),
        'natures': ProductNature.objects.filter(is_active=True),
        'statuses': Product.Status.choices,
    }

    return render(request, 'products/product_form.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def product_delete(request, reference):
    """Delete a product"""
    product = get_object_or_404(Product, reference=reference)

    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de supprimer des produits.')
        return redirect('products:detail', reference=reference)

    # Check if product is sold - warn but still allow deletion
    if product.status == 'sold':
        messages.warning(request, 'Attention: Ce produit est marqué comme vendu.')

    if request.method == 'POST':
        try:
            product_name = product.name
            product_ref = product.reference

            # Delete related images first
            product.images.all().delete()

            # Delete the product
            product.delete()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.DELETE,
                model_name='Product',
                object_id=str(product.id),
                object_repr=product_ref,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Produit "{product_name}" ({product_ref}) supprimé avec succès.')
            return redirect('products:list')

        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('products:detail', reference=reference)

    context = {
        'product': product,
    }

    return render(request, 'products/product_delete.html', context)


# Statuses considered physically in stock (owned, unsold)
INSTOCK_STATUSES = ['available', 'reserved', 'in_repair', 'custom_order']

INVENTORY_SCOPES = {
    'available': (['available'], 'Disponible'),
    'instock': (INSTOCK_STATUSES, 'En boutique (dispo + réservé + réparation)'),
    'all': (None, 'Tous les produits'),
}

# Per-product material value = net weight × purchase price/gram (the cost we paid
# per gram, WITHOUT the selling margin). Falls back to gross weight if net is 0.
_DEC = DecimalField(max_digits=18, decimal_places=2)
_MATERIAL_VALUE_EXPR = Coalesce(
    F('metal_cost'), Coalesce(F('net_weight'), F('gross_weight')) * F('purchase_price_per_gram'),
    output_field=_DEC,
)


def _inventory_scope_qs(scope):
    """Return the Product queryset for the requested inventory scope."""
    statuses, _label = INVENTORY_SCOPES.get(scope, INVENTORY_SCOPES['available'])
    qs = Product.objects.all()
    if statuses is not None:
        qs = qs.filter(status__in=statuses)
    return qs


def _inventory_breakdown(qs, group_field):
    """Aggregate a queryset by a grouping field, valued at material cost."""
    rows = list(
        qs.values(group_field).annotate(
            count=Count('id'),
            gross=Sum('gross_weight'),
            net=Sum('net_weight'),
            material_value=Sum(_MATERIAL_VALUE_EXPR),
            total_cost=Sum('total_cost'),
            selling=Sum('selling_price'),
        ).order_by('-material_value')
    )
    for r in rows:
        r['label'] = r.get(group_field) or '(Non défini)'
    return rows


@login_required(login_url='login')
def inventory_dashboard(request):
    """Cost-based inventory dashboard (material value = poids × prix/g, sans marge)."""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas accès à ce tableau de bord.')
        return redirect('dashboard')

    scope = request.GET.get('scope', 'available')
    if scope not in INVENTORY_SCOPES:
        scope = 'available'
    qs = _inventory_scope_qs(scope)

    # Headline KPIs valued at COST (no margin)
    kpis = qs.aggregate(
        count=Count('id'),
        gross=Sum('gross_weight'),
        net=Sum('net_weight'),
        material_value=Sum(_MATERIAL_VALUE_EXPR),
        total_cost=Sum('total_cost'),
        selling=Sum('selling_price'),
    )
    material_value = kpis['material_value'] or Decimal('0')
    total_cost = kpis['total_cost'] or Decimal('0')
    selling = kpis['selling'] or Decimal('0')

    # Status breakdown across ALL products (overview)
    status_map = dict(Product.Status.choices)
    status_rows = list(
        Product.objects.values('status').annotate(
            count=Count('id'),
            gross=Sum('gross_weight'),
            material_value=Sum(_MATERIAL_VALUE_EXPR),
        ).order_by('-count')
    )
    for r in status_rows:
        r['status_label'] = status_map.get(r['status'], r['status'])

    context = {
        'scope': scope,
        'scope_label': INVENTORY_SCOPES[scope][1],
        'scopes': [(k, v[1]) for k, v in INVENTORY_SCOPES.items()],
        # KPIs
        'stock_count': kpis['count'] or 0,
        'gross_weight': kpis['gross'] or Decimal('0'),
        'net_weight': kpis['net'] or Decimal('0'),
        'material_value': material_value,     # poids × prix/g (sans marge)
        'total_cost': total_cost,             # coût total (matière + façon + pierres)
        'selling_value': selling,             # valeur de vente (avec marge)
        'potential_margin': selling - total_cost,
        # Breakdowns (each downloadable)
        'metal_breakdown': _inventory_breakdown(qs, 'metal_type__name'),
        'purity_breakdown': _inventory_breakdown(qs, 'metal_purity__name'),
        'category_breakdown': _inventory_breakdown(qs, 'category__name'),
        'jewelry_breakdown': _inventory_breakdown(qs, 'jewelry_type__name'),
        'status_breakdown': status_rows,
    }
    return render(request, 'products/inventory_dashboard.html', context)


@login_required(login_url='login')
def inventory_export(request):
    """Download inventory reports as CSV (full item list or any breakdown)."""
    if not request.user.is_staff:
        messages.error(request, 'Accès refusé.')
        return redirect('dashboard')

    scope = request.GET.get('scope', 'available')
    if scope not in INVENTORY_SCOPES:
        scope = 'available'
    report = request.GET.get('report', 'full')
    qs = _inventory_scope_qs(scope)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('﻿')  # UTF-8 BOM so Excel reads accents correctly
    response['Content-Disposition'] = f'attachment; filename="inventaire_{report}_{scope}.csv"'
    writer = csv.writer(response)

    def _num(v):
        return f"{(v or 0):.2f}"

    if report == 'full':
        writer.writerow([
            'Référence', 'Nom', 'Statut', 'Catégorie', 'Type bijou', 'Métal', 'Pureté',
            'Poids brut (g)', 'Poids net (g)', 'Prix/g (DH)',
            'Valeur matière (DH)', 'Coût total (DH)', 'Prix de vente (DH)',
        ])
        items = qs.select_related(
            'category', 'jewelry_type', 'metal_type', 'metal_purity'
        ).order_by('category__name', 'reference')
        for p in items:
            net = p.net_weight or p.gross_weight or Decimal('0')
            material = p.metal_cost if p.metal_cost else (net * (p.purchase_price_per_gram or Decimal('0')))
            writer.writerow([
                p.reference, p.name, p.get_status_display(),
                p.category.name if p.category else '',
                p.jewelry_type.name if p.jewelry_type else '',
                p.metal_type.name if p.metal_type else '',
                p.metal_purity.name if p.metal_purity else '',
                _num(p.gross_weight), _num(p.net_weight), _num(p.purchase_price_per_gram),
                _num(material), _num(p.total_cost), _num(p.selling_price),
            ])
        return response

    # Breakdown reports
    group_fields = {
        'metal': ('metal_type__name', 'Métal'),
        'purity': ('metal_purity__name', 'Pureté'),
        'category': ('category__name', 'Catégorie'),
        'jewelry': ('jewelry_type__name', 'Type bijou'),
    }
    if report == 'status':
        status_map = dict(Product.Status.choices)
        rows = list(Product.objects.values('status').annotate(
            count=Count('id'), gross=Sum('gross_weight'), net=Sum('net_weight'),
            material_value=Sum(_MATERIAL_VALUE_EXPR), total_cost=Sum('total_cost'),
            selling=Sum('selling_price'),
        ).order_by('-count'))
        writer.writerow(['Statut', 'Nb', 'Poids brut (g)', 'Poids net (g)', 'Valeur matière (DH)', 'Coût total (DH)', 'Valeur vente (DH)'])
        for r in rows:
            writer.writerow([
                status_map.get(r['status'], r['status']), r['count'],
                _num(r['gross']), _num(r['net']), _num(r['material_value']), _num(r['total_cost']), _num(r['selling']),
            ])
        return response

    if report in group_fields:
        field, label = group_fields[report]
        rows = _inventory_breakdown(qs, field)
        writer.writerow([label, 'Nb', 'Poids brut (g)', 'Poids net (g)', 'Valeur matière (DH)', 'Coût total (DH)', 'Valeur vente (DH)'])
        for r in rows:
            writer.writerow([
                r[field] or '(Non défini)', r['count'],
                _num(r['gross']), _num(r['net']), _num(r['material_value']), _num(r['total_cost']), _num(r['selling']),
            ])
        return response

    # Unknown report
    writer.writerow(['Rapport inconnu'])
    return response


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
    """Print a product label - tries direct print first, then queues if unreachable"""
    product = get_object_or_404(Product, reference=reference)

    label_type = request.POST.get('label_type', 'product')
    quantity = int(request.POST.get('quantity', 1))

    if quantity < 1 or quantity > 10:
        quantity = 1

    # Generate ZPL data
    if label_type == 'price':
        zpl_data = generate_price_tag_zpl(product, quantity)
    else:
        zpl_data = generate_product_label_zpl(product, quantity)

    # Try direct print first, fall back to queue
    success, message = print_product_label(product, quantity) if label_type != 'price' else print_price_tag(product, quantity)

    # If direct print failed, add to queue
    queued = False
    if not success:
        queue_success, queue_message = queue_print_job(
            zpl_data=zpl_data,
            product=product,
            label_type=label_type,
            quantity=quantity,
            user=request.user
        )
        if queue_success:
            success = True
            message = f"Imprimante inaccessible. {queue_message}"
            queued = True

    # Log activity
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.PRINT,
        model_name='Product',
        object_id=str(product.id),
        object_repr=f"{product.reference} - {label_type} x{quantity}" + (" (queued)" if queued else ""),
        ip_address=get_client_ip(request)
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': success, 'message': message, 'queued': queued})

    if success:
        if queued:
            messages.info(request, f'Étiquette ajoutée à la file d\'impression pour {product.reference}')
        else:
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


@login_required(login_url='login')
def printer_debug(request):
    """Debug endpoint to check printer configuration and test connection"""
    import socket
    from .print_utils import get_printer_settings
    from settings_app.models import SystemConfig

    try:
        config = SystemConfig.get_config()
        db_ip = config.zebra_printer_ip
        db_port = config.zebra_printer_port
        db_enabled = config.zebra_printer_enabled
    except Exception as e:
        db_ip = f"Error: {e}"
        db_port = None
        db_enabled = None

    active_ip, active_port = get_printer_settings()

    # Test connection to printer
    connection_test = {
        'tested': False,
        'success': False,
        'message': 'Not tested'
    }

    if active_ip and active_port:
        connection_test['tested'] = True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 5 second timeout for test
            sock.connect((active_ip, active_port))
            sock.close()
            connection_test['success'] = True
            connection_test['message'] = f'Successfully connected to {active_ip}:{active_port}'
        except socket.timeout:
            connection_test['message'] = f'Connection timeout to {active_ip}:{active_port}'
        except ConnectionRefusedError:
            connection_test['message'] = f'Connection refused by {active_ip}:{active_port}'
        except Exception as e:
            connection_test['message'] = f'Connection error: {str(e)}'

    return JsonResponse({
        'database_config': {
            'ip': str(db_ip) if db_ip else None,
            'port': db_port,
            'enabled': db_enabled,
        },
        'active_config': {
            'ip': active_ip,
            'port': active_port,
        },
        'connection_test': connection_test
    })


@login_required(login_url='login')
def printer_config_api(request):
    """API endpoint to get printer configuration for browser-based printing"""
    from settings_app.models import SystemConfig

    try:
        config = SystemConfig.get_config()
        return JsonResponse({
            'ip': str(config.zebra_printer_ip) if config.zebra_printer_ip else None,
            'port': config.zebra_printer_port or 9100,
            'enabled': config.zebra_printer_enabled,
            'http_url': f'http://{config.zebra_printer_ip}/pstprnt' if config.zebra_printer_ip else None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='login')
def product_zpl_api(request, reference):
    """API endpoint to get ZPL data for a product (for browser-based printing)"""
    product = get_object_or_404(Product, reference=reference)

    label_type = request.GET.get('label_type', 'product')
    quantity = int(request.GET.get('quantity', 1))

    if quantity < 1 or quantity > 10:
        quantity = 1

    if label_type == 'price':
        zpl_data = generate_price_tag_zpl(product, quantity)
    else:
        zpl_data = generate_product_label_zpl(product, quantity)

    return JsonResponse({
        'zpl': zpl_data,
        'product': product.reference,
        'label_type': label_type,
        'quantity': quantity
    })


# =============================================================================
# Image Enhancement API
# =============================================================================

@login_required(login_url='login')
@require_http_methods(["POST"])
def enhance_image_api(request, reference):
    """
    Enhance a product image.
    mode='background': remove bg + solid color (local rembg)
    mode='model': generate product-on-model photo via fal.ai
    """
    import json
    import os
    import logging
    import requests as http_requests
    from django.core.files.base import ContentFile
    from .models import ProductImage

    log = logging.getLogger(__name__)
    product = get_object_or_404(Product, reference=reference)

    body = json.loads(request.body) if request.body else {}
    mode = body.get('mode', 'background')
    background = body.get('background', 'white')
    image_id = body.get('image_id')

    # Get the source image
    if image_id:
        img_obj = get_object_or_404(ProductImage, id=image_id, product=product)
        source_image = img_obj.image
    else:
        from .ai_image_utils import get_source_image
        source_image = get_source_image(product)
        if not source_image:
            return JsonResponse({'success': False, 'error': 'Aucune image a ameliorer'}, status=400)

    if mode == 'model':
        # Fal.ai: generate product-on-model photo
        try:
            from ai_services.fal_client import enhance_product_image, is_configured, image_file_to_data_uri

            if not is_configured():
                return JsonResponse({'success': False, 'error': 'Cle API fal.ai non configuree (FAL_AI_KEY)'}, status=500)

            # Convert local file to base64 data URI (avoids Cloudflare blocking fal.ai)
            image_url = image_file_to_data_uri(source_image.path)

            category_name = product.category.name if product.category else None
            result = enhance_product_image(image_url, category_name=category_name, mode='model')

            # Download the generated image and save it
            img_response = http_requests.get(result['url'], timeout=30)
            img_response.raise_for_status()

            filename = f"model_{os.path.basename(source_image.name)}"
            if not filename.lower().endswith('.jpg'):
                filename = filename.rsplit('.', 1)[0] + '.jpg'

            new_img = ProductImage(product=product, display_order=99)
            new_img.image.save(filename, ContentFile(img_response.content), save=True)

            # Mark AI image as completed
            from django.utils import timezone as tz
            product.ai_image_status = Product.AIImageStatus.COMPLETED
            product.ai_image_completed_at = tz.now()
            product.ai_image_error = None
            product.save(update_fields=['ai_image_status', 'ai_image_completed_at', 'ai_image_error'])

            return JsonResponse({
                'success': True,
                'image_url': new_img.image.url,
                'image_id': new_img.id,
                'message': 'Photo sur modele generee avec succes'
            })
        except Exception as e:
            log.error(f'Fal.ai model photo failed: {e}')
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        # Local: rembg background removal
        try:
            from .image_enhance import process_product_image
            import io

            result = process_product_image(source_image.path, background=background)

            buffer = io.BytesIO()
            result.save(buffer, 'JPEG', quality=92, optimize=True)
            buffer.seek(0)

            filename = f"enhanced_{background}_{os.path.basename(source_image.name)}"
            if not filename.lower().endswith('.jpg'):
                filename = filename.rsplit('.', 1)[0] + '.jpg'

            new_img = ProductImage(product=product, display_order=99)
            new_img.image.save(filename, ContentFile(buffer.read()), save=True)

            return JsonResponse({
                'success': True,
                'image_url': new_img.image.url,
                'image_id': new_img.id,
                'message': f'Image amelioree avec fond {background}'
            })
        except ImportError:
            return JsonResponse({'success': False, 'error': 'rembg non installe sur le serveur. Executez: pip install rembg[cpu]'}, status=500)
        except Exception as e:
            logger.error(f'Image enhancement failed: {e}')
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =============================================================================
# Print Direct API - Server sends ZPL to printer via TCP (for mobile devices)
# =============================================================================

@login_required(login_url='login')
@require_http_methods(["POST"])
def print_direct_api(request):
    """
    API endpoint for mobile devices to print via server.
    Mobile browsers can't reach the printer's local IP directly,
    so this endpoint receives ZPL data and sends it to the printer via TCP.
    """
    import json
    try:
        data = json.loads(request.body)
        zpl_data = data.get('zpl', '')
        if not zpl_data:
            return JsonResponse({'success': False, 'message': 'Pas de donnees ZPL'}, status=400)

        success, message = send_to_printer(zpl_data)
        return JsonResponse({'success': success, 'message': message})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Donnees invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


# =============================================================================
# Product Image Upload API - For direct upload from product detail page
# =============================================================================

@login_required(login_url='login')
@require_http_methods(["POST"])
def product_image_upload_api(request, reference):
    """API endpoint to upload images directly from the product detail page"""
    product = get_object_or_404(Product, reference=reference)

    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)

    images = request.FILES.getlist('images')
    if not images:
        return JsonResponse({'success': False, 'message': 'Aucune image sélectionnée'})

    uploaded = []
    existing_count = product.images.count()

    for i, image_file in enumerate(images):
        try:
            converted_image = convert_image_to_jpeg(image_file)
            product_image = ProductImage.objects.create(
                product=product,
                image=converted_image,
                is_primary=False,
                display_order=existing_count + i
            )

            # Set as main_image if none exists
            if not product.main_image and not product.images.filter(is_primary=True).exists():
                product_image.is_primary = True
                product_image.save()

            uploaded.append({
                'id': product_image.id,
                'url': product_image.image.url,
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})

    # If images were added and the product was previously skipped,
    # reset AI status so cron picks it up
    if uploaded and product.ai_image_status == Product.AIImageStatus.SKIPPED:
        product.ai_image_status = Product.AIImageStatus.PENDING
        product.save(update_fields=['ai_image_status'])

    # Log activity
    try:
        ActivityLog.objects.create(
            user=request.user,
            action='upload_image',
            description=f"Ajout de {len(uploaded)} image(s) au produit {product.reference}"
        )
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'message': f'{len(uploaded)} image(s) ajoutée(s)',
        'images': uploaded
    })


# Max video size in bytes (200 MB)
MAX_VIDEO_SIZE = 200 * 1024 * 1024


@login_required(login_url='login')
@require_http_methods(["POST"])
def product_video_upload_api(request, reference):
    """Upload one or more videos for a product. Transcodes to MP4 H.264 via ffmpeg."""
    product = get_object_or_404(Product, reference=reference)

    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)

    videos = request.FILES.getlist('videos')
    if not videos:
        return JsonResponse({'success': False, 'message': 'Aucune vidéo sélectionnée'})

    uploaded = []
    existing_count = product.videos.count()

    for i, video_file in enumerate(videos):
        if video_file.size > MAX_VIDEO_SIZE:
            return JsonResponse({
                'success': False,
                'message': f'Vidéo trop volumineuse ({video_file.name}). Max 200 MB.'
            }, status=400)
        try:
            result = convert_video_to_mp4(video_file)

            product_video = ProductVideo(
                product=product,
                display_order=existing_count + i,
                duration_seconds=result.get('duration'),
                file_size_bytes=result.get('size'),
                created_by=request.user,
            )
            product_video.video.save(result['video_name'], result['video'], save=False)
            if result.get('poster'):
                product_video.poster.save(result['poster_name'], result['poster'], save=False)
            product_video.save()

            uploaded.append({
                'id': product_video.id,
                'url': product_video.video.url,
                'poster_url': product_video.poster.url if product_video.poster else None,
                'duration': product_video.duration_seconds,
                'converted': result.get('converted', False),
            })
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception('Video upload failed')
            return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'}, status=500)

    try:
        ActivityLog.objects.create(
            user=request.user,
            action='upload_video',
            description=f"Ajout de {len(uploaded)} vidéo(s) au produit {product.reference}"
        )
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'message': f'{len(uploaded)} vidéo(s) ajoutée(s)',
        'videos': uploaded,
    })


@login_required(login_url='login')
@require_http_methods(["POST", "DELETE"])
def product_video_delete_api(request, video_id):
    """Delete a ProductVideo by id. Staff only."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)

    video = get_object_or_404(ProductVideo, pk=video_id)
    reference = video.product.reference
    try:
        if video.video:
            video.video.delete(save=False)
        if video.poster:
            video.poster.delete(save=False)
        video.delete()
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'}, status=500)

    try:
        ActivityLog.objects.create(
            user=request.user,
            action='delete_video',
            description=f"Suppression d'une vidéo du produit {reference}"
        )
    except Exception:
        pass

    return JsonResponse({'success': True, 'message': 'Vidéo supprimée'})


# =============================================================================
# Product Search API - For barcode scanner
# =============================================================================

@login_required(login_url='login')
def product_search_api(request):
    """
    Search products by barcode / reference / RFID / name.

    Additive extensions (existing callers unaffected):
      * response includes weight, purity, metal, category, price_per_gram
      * optional filters combinable with q:
          weight=2.730            exact weight (net or gross)
          weight_min= / weight_max=   weight range
          status=available|sold|...   default: all
          limit=<n>               default 10, max 100
    """
    query = request.GET.get('q', '').strip()

    def _dec(name):
        raw = (request.GET.get(name) or '').strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return None

    weight = _dec('weight')
    weight_min = _dec('weight_min')
    weight_max = _dec('weight_max')
    status_filter = (request.GET.get('status') or '').strip()
    has_filter = any(v is not None for v in (weight, weight_min, weight_max)) or bool(status_filter)

    # Preserve original behaviour: nothing to search -> empty result
    if not query and not has_filter:
        return JsonResponse({'products': []})

    qs = Product.objects.select_related('category', 'metal_type', 'metal_purity')

    # Same cascade as before: first matching lookup type wins
    if query:
        by_barcode = qs.filter(barcode=query)
        if by_barcode.exists():
            qs = by_barcode
        else:
            by_ref = qs.filter(reference__icontains=query)
            if by_ref.exists():
                qs = by_ref
            else:
                by_rfid = qs.filter(rfid_tag__icontains=query)
                if by_rfid.exists():
                    qs = by_rfid
                else:
                    qs = qs.filter(name__icontains=query)

    # Optional filters
    if weight is not None:
        qs = qs.filter(Q(net_weight=weight) | Q(gross_weight=weight))
    if weight_min is not None:
        qs = qs.filter(net_weight__gte=weight_min)
    if weight_max is not None:
        qs = qs.filter(net_weight__lte=weight_max)
    if status_filter:
        qs = qs.filter(status=status_filter)

    try:
        limit = min(max(int(request.GET.get('limit', 10)), 1), 100)
    except (ValueError, TypeError):
        limit = 10
    products = qs[:limit]

    results = []
    for p in products:
        w = p.net_weight if p.net_weight is not None else p.gross_weight
        results.append({
            'id': p.id,
            'reference': p.reference,
            'name': p.name,
            'barcode': p.barcode,
            'status': p.status,
            'selling_price': str(p.selling_price) if p.selling_price is not None else None,
            # additive fields
            'weight': str(w) if w is not None else None,
            'purity': p.metal_purity.name if p.metal_purity else None,
            'metal': p.metal_type.name if p.metal_type else None,
            'category': p.category.name if p.category else None,
            'price_per_gram': str(p.purchase_price_per_gram) if p.purchase_price_per_gram is not None else None,
        })

    return JsonResponse({'products': results})


@login_required(login_url='login')
def server_images_api(request):
    """API endpoint to browse existing images in media/products/ directory"""
    from django.conf import settings
    import glob

    search = request.GET.get('search', '').strip().lower()
    page = int(request.GET.get('page', 1))
    per_page = 24

    products_dir = os.path.join(settings.MEDIA_ROOT, 'products')
    if not os.path.isdir(products_dir):
        return JsonResponse({'images': [], 'has_next': False, 'total': 0})

    # List image files
    extensions = ('*.jpg', '*.jpeg', '*.png', '*.webp')
    all_files = []
    for ext in extensions:
        all_files.extend(glob.glob(os.path.join(products_dir, ext)))
        all_files.extend(glob.glob(os.path.join(products_dir, ext.upper())))

    # Deduplicate and sort by modification time (newest first)
    all_files = list(set(all_files))
    all_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    # Filter by search
    if search:
        all_files = [f for f in all_files if search in os.path.basename(f).lower()]

    total = len(all_files)
    start = (page - 1) * per_page
    end = start + per_page
    page_files = all_files[start:end]

    images = []
    for filepath in page_files:
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        images.append({
            'url': f'{settings.MEDIA_URL}products/{filename}',
            'filename': filename,
            'size': size,
        })

    return JsonResponse({
        'images': images,
        'has_next': end < total,
        'total': total,
        'page': page,
    })


@login_required(login_url='login')
def smart_search_api(request):
    """AI-powered semantic product search - falls back to keyword if AI unavailable."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'products': []})

    # First try keyword search
    keyword_results = Product.objects.filter(
        Q(reference__icontains=query) |
        Q(name__icontains=query) |
        Q(name_ar__icontains=query) |
        Q(barcode__icontains=query) |
        Q(description__icontains=query) |
        Q(category__name__icontains=query)
    ).select_related('category', 'metal_type', 'metal_purity', 'jewelry_type')[:10]

    # If keyword search found results, use those
    if keyword_results.exists():
        results = _format_product_results(keyword_results)
        return JsonResponse({'products': results, 'search_type': 'keyword'})

    # Fall back to semantic search
    try:
        from ai_services.embeddings import search_products as semantic_search
        semantic_results = semantic_search(query, top_k=10, min_score=0.3)

        if semantic_results:
            product_ids = [r['product_id'] for r in semantic_results]
            products = Product.objects.filter(
                id__in=product_ids
            ).select_related('category', 'metal_type', 'metal_purity', 'jewelry_type')

            # Maintain score ordering
            products_dict = {p.id: p for p in products}
            ordered = [products_dict[pid] for pid in product_ids if pid in products_dict]

            results = _format_product_results(ordered)
            return JsonResponse({'products': results, 'search_type': 'semantic'})
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Semantic search error: {e}')

    return JsonResponse({'products': [], 'search_type': 'none'})


def _format_product_results(products):
    """Format products for JSON response."""
    return [{
        'id': p.id,
        'reference': p.reference,
        'name': p.name,
        'category': p.category.name if p.category else '',
        'metal': f"{p.metal_type.name if p.metal_type else ''} {p.metal_purity.name if p.metal_purity else ''}".strip(),
        'weight': str(p.gross_weight or 0),
        'selling_price': str(p.selling_price) if p.selling_price else None,
        'status': p.status,
    } for p in products]


# =============================================================================
# Print Queue API - For local print agent
# =============================================================================

@login_required(login_url='login')
def print_queue_view(request):
    """Display print queue UI"""
    from .models import PrintQueue

    # Handle actions
    if request.method == 'POST':
        action = request.POST.get('action')
        job_ids = request.POST.getlist('job_ids')

        if action == 'cancel' and job_ids:
            PrintQueue.objects.filter(
                id__in=job_ids,
                status=PrintQueue.Status.PENDING
            ).update(status=PrintQueue.Status.CANCELLED)
            messages.success(request, f'{len(job_ids)} job(s) annulé(s)')

        elif action == 'retry' and job_ids:
            PrintQueue.objects.filter(
                id__in=job_ids,
                status__in=[PrintQueue.Status.FAILED, PrintQueue.Status.CANCELLED]
            ).update(status=PrintQueue.Status.PENDING, attempts=0, error_message='')
            messages.success(request, f'{len(job_ids)} job(s) relancé(s)')

        elif action == 'delete' and job_ids:
            PrintQueue.objects.filter(id__in=job_ids).delete()
            messages.success(request, f'{len(job_ids)} job(s) supprimé(s)')

        return redirect('products:print_queue')

    # Get jobs with filtering
    status_filter = request.GET.get('status', '')
    jobs = PrintQueue.objects.select_related('product', 'created_by').order_by('-created_at')

    if status_filter:
        jobs = jobs.filter(status=status_filter)

    # Pagination
    paginator = Paginator(jobs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Stats
    stats = {
        'pending': PrintQueue.objects.filter(status=PrintQueue.Status.PENDING).count(),
        'printing': PrintQueue.objects.filter(status=PrintQueue.Status.PRINTING).count(),
        'printed': PrintQueue.objects.filter(status=PrintQueue.Status.PRINTED).count(),
        'failed': PrintQueue.objects.filter(status=PrintQueue.Status.FAILED).count(),
    }

    context = {
        'page_obj': page_obj,
        'jobs': page_obj.object_list,
        'status_filter': status_filter,
        'statuses': PrintQueue.Status.choices,
        'stats': stats,
    }

    return render(request, 'products/print_queue.html', context)


def print_queue_list(request):
    """
    API endpoint to list print queue jobs.
    Used by the local print agent.
    Requires API key authentication.
    """
    from .models import PrintQueue
    from django.conf import settings
    import json

    # Check API key
    api_key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    expected_key = getattr(settings, 'PRINT_API_KEY', 'hafsa-print-2024')

    if api_key != expected_key:
        return JsonResponse({'error': 'Invalid API key'}, status=401)

    # Get all jobs with optional status filter
    status = request.GET.get('status')
    jobs = PrintQueue.objects.select_related('product').order_by('created_at')

    if status:
        jobs = jobs.filter(status=status)

    jobs_data = []
    for job in jobs[:100]:  # Limit to 100 jobs
        jobs_data.append({
            'id': job.id,
            'product_reference': job.product.reference if job.product else None,
            'label_type': job.label_type,
            'quantity': job.quantity,
            'status': job.status,
            'zpl_data': job.zpl_data,
            'attempts': job.attempts,
            'error_message': job.error_message,
            'created_at': job.created_at.isoformat(),
        })

    return JsonResponse({'jobs': jobs_data})


def print_queue_pending(request):
    """
    API endpoint to get pending print jobs.
    Used by the local print agent to fetch jobs to print.
    """
    from .models import PrintQueue
    from django.conf import settings
    from django.utils import timezone

    # Check API key
    api_key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    expected_key = getattr(settings, 'PRINT_API_KEY', 'hafsa-print-2024')

    if api_key != expected_key:
        return JsonResponse({'error': 'Invalid API key'}, status=401)

    # Get pending jobs (oldest first)
    pending_jobs = PrintQueue.objects.filter(
        status=PrintQueue.Status.PENDING
    ).select_related('product').order_by('created_at')[:10]  # Process 10 at a time

    # Mark them as printing
    job_ids = [job.id for job in pending_jobs]
    if job_ids:
        PrintQueue.objects.filter(id__in=job_ids).update(
            status=PrintQueue.Status.PRINTING
        )

    jobs_data = []
    for job in pending_jobs:
        jobs_data.append({
            'id': job.id,
            'product_reference': job.product.reference if job.product else None,
            'label_type': job.label_type,
            'quantity': job.quantity,
            'zpl_data': job.zpl_data,
        })

    return JsonResponse({
        'jobs': jobs_data,
        'total_pending': PrintQueue.get_pending_count()
    })


@require_http_methods(["POST"])
def print_queue_complete(request, job_id):
    """
    API endpoint to mark a print job as completed.
    Called by the local print agent after successful print.
    """
    from .models import PrintQueue
    from django.conf import settings
    from django.utils import timezone

    # Check API key
    api_key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    expected_key = getattr(settings, 'PRINT_API_KEY', 'hafsa-print-2024')

    if api_key != expected_key:
        return JsonResponse({'error': 'Invalid API key'}, status=401)

    try:
        job = PrintQueue.objects.get(id=job_id)
        job.status = PrintQueue.Status.PRINTED
        job.printed_at = timezone.now()
        job.save()
        return JsonResponse({'success': True, 'message': 'Job marked as printed'})
    except PrintQueue.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)


@require_http_methods(["POST"])
def print_queue_fail(request, job_id):
    """
    API endpoint to mark a print job as failed.
    Called by the local print agent after failed print attempt.
    """
    from .models import PrintQueue
    from django.conf import settings
    import json

    # Check API key
    api_key = request.headers.get('X-API-Key') or request.GET.get('api_key')
    expected_key = getattr(settings, 'PRINT_API_KEY', 'hafsa-print-2024')

    if api_key != expected_key:
        return JsonResponse({'error': 'Invalid API key'}, status=401)

    try:
        job = PrintQueue.objects.get(id=job_id)

        # Get error message from request body
        try:
            data = json.loads(request.body)
            error_message = data.get('error', 'Unknown error')
        except:
            error_message = request.POST.get('error', 'Unknown error')

        job.attempts += 1
        job.error_message = error_message

        # If max attempts reached, mark as failed
        if job.attempts >= 3:
            job.status = PrintQueue.Status.FAILED
        else:
            # Reset to pending for retry
            job.status = PrintQueue.Status.PENDING

        job.save()

        return JsonResponse({
            'success': True,
            'message': f'Job attempt {job.attempts} recorded',
            'status': job.status,
            'will_retry': job.status == PrintQueue.Status.PENDING
        })
    except PrintQueue.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)


# =============================================================================
# Catalog (token-based public access for online team)
# =============================================================================

def public_catalog(request):
    """Public catalog page for clients (no prices, no login required)."""
    context = {
        'categories': ProductCategory.objects.filter(is_active=True).order_by('display_order', 'name'),
        'metal_types': MetalType.objects.filter(is_active=True).order_by('name'),
        'metal_purities': MetalPurity.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'products/public_catalog.html', context)


def public_catalog_api(request):
    """JSON API for the public catalog. No prices/cost fields exposed."""
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    metal_type = request.GET.get('metal_type', '')
    purity = request.GET.get('purity', '')
    weight_min = request.GET.get('weight_min', '')
    weight_max = request.GET.get('weight_max', '')
    sort = request.GET.get('sort', 'date_desc')
    page = int(request.GET.get('page', 1))
    per_page = min(int(request.GET.get('per_page', 24)), 50)

    qs = Product.objects.filter(
        status=Product.Status.AVAILABLE
    ).select_related('category', 'metal_type', 'metal_purity', 'jewelry_type').prefetch_related('images')

    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(reference__icontains=q) |
            Q(category__name__icontains=q)
        )
    if category:
        qs = qs.filter(category_id=category)
    if metal_type:
        qs = qs.filter(metal_type_id=metal_type)
    if purity:
        qs = qs.filter(metal_purity_id=purity)
    if weight_min:
        qs = qs.filter(gross_weight__gte=weight_min)
    if weight_max:
        qs = qs.filter(gross_weight__lte=weight_max)

    valid_sorts = {
        'weight_asc': 'gross_weight',
        'weight_desc': '-gross_weight',
        'date_asc': 'created_at',
        'date_desc': '-created_at',
        'name_asc': 'name',
        'name_desc': '-name',
    }
    qs = qs.order_by(valid_sorts.get(sort, '-created_at'))

    total = qs.count()
    start = (page - 1) * per_page
    products = qs[start:start + per_page]

    results = []
    for p in products:
        ai_images = []
        original_images = []
        if p.main_image:
            original_images.append(p.main_image.url)
        for img in p.images.all():
            img_url = img.image.url if img.image else None
            if img_url:
                if 'model_' in os.path.basename(img.image.name):
                    ai_images.append(img_url)
                elif img_url not in original_images:
                    original_images.append(img_url)
        image_url = ai_images[0] if ai_images else (original_images[0] if original_images else None)

        results.append({
            'id': p.id,
            'reference': p.reference,
            'name': p.name,
            'category': p.category.name if p.category else '',
            'metal': p.metal_type.name if p.metal_type else '',
            'purity': p.metal_purity.name if p.metal_purity else '',
            'weight': str(p.gross_weight or 0),
            'image_url': image_url,
            'all_images': ai_images + original_images,
        })

    pages = (total + per_page - 1) // per_page
    return JsonResponse({
        'products': results,
        'total': total,
        'page': page,
        'pages': pages,
        'has_next': page < pages,
    })


def _get_catalog_token(token):
    """Validate catalog token. Returns CatalogToken or None."""
    from .models import CatalogToken
    try:
        return CatalogToken.objects.get(token=token, is_active=True)
    except CatalogToken.DoesNotExist:
        return None


def _catalog_session_key(token_id):
    return f'catalog_auth_{token_id}'


def _catalog_is_authenticated(request, catalog_token):
    """Token has no password OR session marks this token as authed."""
    if not catalog_token.password_hash:
        return True
    return bool(request.session.get(_catalog_session_key(catalog_token.id)))


def _catalog_throttle_key(request, token_str):
    ip = get_client_ip(request) or 'unknown'
    return f'catalog_throttle:{token_str}:{ip}'


def _catalog_check_throttle(request, token_str):
    """Returns (is_throttled, attempts_remaining). Max 5 fails per 15 min."""
    from django.core.cache import cache
    key = _catalog_throttle_key(request, token_str)
    attempts = cache.get(key, 0)
    return attempts >= 5, max(0, 5 - attempts)


def _catalog_record_failure(request, token_str):
    from django.core.cache import cache
    key = _catalog_throttle_key(request, token_str)
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, 15 * 60)  # 15 minutes
    return attempts


def _catalog_clear_throttle(request, token_str):
    from django.core.cache import cache
    cache.delete(_catalog_throttle_key(request, token_str))


def catalog_view(request, token):
    """Render the catalog page for the online team. Requires per-token password."""
    from .models import CatalogAccessLog
    catalog_token = _get_catalog_token(token)
    if not catalog_token:
        return render(request, 'products/catalog_invalid.html', status=403)

    # Login flow if password protected
    if catalog_token.password_hash and not _catalog_is_authenticated(request, catalog_token):
        if request.method == 'POST':
            is_throttled, _remaining = _catalog_check_throttle(request, token)
            if is_throttled:
                return render(request, 'products/catalog_login.html', {
                    'token': token,
                    'catalog_name': catalog_token.name,
                    'error': 'Trop de tentatives. Réessayez dans 15 minutes.',
                }, status=429)

            password = request.POST.get('password', '')
            if catalog_token.check_password(password):
                _catalog_clear_throttle(request, token)
                request.session[_catalog_session_key(catalog_token.id)] = True
                # Sliding session: 8 hours
                request.session.set_expiry(8 * 60 * 60)
                # Log access
                from django.utils import timezone
                CatalogAccessLog.objects.create(
                    token=catalog_token,
                    ip_address=get_client_ip(request),
                    user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:500],
                )
                catalog_token.last_accessed_at = timezone.now()
                catalog_token.access_count = (catalog_token.access_count or 0) + 1
                catalog_token.save(update_fields=['last_accessed_at', 'access_count'])
                return redirect('products:catalog', token=token)
            else:
                attempts = _catalog_record_failure(request, token)
                remaining = max(0, 5 - attempts)
                return render(request, 'products/catalog_login.html', {
                    'token': token,
                    'catalog_name': catalog_token.name,
                    'error': f'Mot de passe incorrect. {remaining} tentative(s) restante(s).',
                }, status=401)

        # GET: show login form
        return render(request, 'products/catalog_login.html', {
            'token': token,
            'catalog_name': catalog_token.name,
        })

    context = {
        'token': token,
        'catalog_name': catalog_token.name,
        'categories': ProductCategory.objects.filter(is_active=True).order_by('display_order', 'name'),
        'metal_types': MetalType.objects.filter(is_active=True).order_by('name'),
        'metal_purities': MetalPurity.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'products/catalog.html', context)


def catalog_api(request, token):
    """JSON API for filtered product listing."""
    catalog_token = _get_catalog_token(token)
    if not catalog_token:
        return JsonResponse({'error': 'Token invalide'}, status=403)

    if not _catalog_is_authenticated(request, catalog_token):
        return JsonResponse({'error': 'Authentification requise'}, status=401)

    # Parse filters
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    metal_type = request.GET.get('metal_type', '')
    purity = request.GET.get('purity', '')
    price_min = request.GET.get('price_min', '')
    price_max = request.GET.get('price_max', '')
    cost_min = request.GET.get('cost_min', '')
    cost_max = request.GET.get('cost_max', '')
    weight_min = request.GET.get('weight_min', '')
    weight_max = request.GET.get('weight_max', '')
    size_min = request.GET.get('size_min', '').strip()
    size_max = request.GET.get('size_max', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    sort = request.GET.get('sort', 'date_desc')
    page = int(request.GET.get('page', 1))
    per_page = min(int(request.GET.get('per_page', 20)), 50)

    # Base queryset: only available products
    qs = Product.objects.filter(
        status=Product.Status.AVAILABLE
    ).select_related(
        'category', 'metal_type', 'metal_purity'
    ).prefetch_related('images')

    # Text search
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(reference__icontains=q) |
            Q(barcode__icontains=q) |
            Q(category__name__icontains=q)
        )

    # Dropdown filters
    if category:
        qs = qs.filter(category_id=category)
    if metal_type:
        qs = qs.filter(metal_type_id=metal_type)
    if purity:
        qs = qs.filter(metal_purity_id=purity)

    # Range filters
    if price_min:
        qs = qs.filter(selling_price__gte=price_min)
    if price_max:
        qs = qs.filter(selling_price__lte=price_max)
    if cost_min:
        qs = qs.filter(total_cost__gte=cost_min)
    if cost_max:
        qs = qs.filter(total_cost__lte=cost_max)
    if weight_min:
        qs = qs.filter(gross_weight__gte=weight_min)
    if weight_max:
        qs = qs.filter(gross_weight__lte=weight_max)

    # Size range: size is free text ("53 cm", "18", "16.5"); parse its numeric
    # part and filter on that so Min/Max work like the weight range.
    def _to_float(v):
        try:
            return float(str(v).replace(',', '.'))
        except (TypeError, ValueError):
            return None
    smin = _to_float(size_min) if size_min else None
    smax = _to_float(size_max) if size_max else None
    if smin is not None or smax is not None:
        import re as _re
        keep = []
        for pid, sval in qs.values_list('id', 'size'):
            if not sval:
                continue
            m = _re.search(r'\d+(?:[.,]\d+)?', sval)
            if not m:
                continue
            num = float(m.group(0).replace(',', '.'))
            if smin is not None and num < smin:
                continue
            if smax is not None and num > smax:
                continue
            keep.append(pid)
        qs = qs.filter(id__in=keep)

    # Date filters
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Sorting
    valid_sorts = {
        'price_asc': 'selling_price',
        'price_desc': '-selling_price',
        'cost_asc': 'total_cost',
        'cost_desc': '-total_cost',
        'date_asc': 'created_at',
        'date_desc': '-created_at',
        'weight_asc': 'gross_weight',
        'weight_desc': '-gross_weight',
        'name_asc': 'name',
        'name_desc': '-name',
    }
    order = valid_sorts.get(sort, '-created_at')
    qs = qs.order_by(order)

    # Pagination
    total = qs.count()
    start = (page - 1) * per_page
    products = qs[start:start + per_page]

    # Format results
    results = []
    for p in products:
        # Separate AI-generated and original images
        ai_images = []
        original_images = []

        if p.main_image:
            original_images.append(p.main_image.url)

        for img in p.images.all():
            img_url = img.image.url if img.image else None
            if img_url:
                if 'model_' in os.path.basename(img.image.name):
                    ai_images.append(img_url)
                elif img_url not in original_images:
                    original_images.append(img_url)

        # Best display image: AI first, then original
        image_url = ai_images[0] if ai_images else (original_images[0] if original_images else None)

        # Price per gram
        price_per_gram = str(p.purchase_price_per_gram or 0)

        results.append({
            'id': p.id,
            'reference': p.reference,
            'name': p.name,
            'category': p.category.name if p.category else '',
            'metal': p.metal_type.name if p.metal_type else '',
            'purity': p.metal_purity.name if p.metal_purity else '',
            'weight': str(p.gross_weight or 0),
            'size': p.size or '',
            'price_per_gram': price_per_gram,
            'total_cost': str(p.total_cost or 0),
            'selling_price': str(p.selling_price or 0),
            'image_url': image_url,
            'ai_images': ai_images,
            'original_images': original_images,
            'all_images': ai_images + original_images,
            'created_at': p.created_at.strftime('%Y-%m-%d') if p.created_at else '',
        })

    pages = (total + per_page - 1) // per_page

    return JsonResponse({
        'products': results,
        'total': total,
        'page': page,
        'pages': pages,
        'has_next': page < pages,
    })


def _catalog_require_user(request, token):
    """Common guard for catalog 'my-data' views. Returns (catalog_token, error_response).
    error_response is non-None if request should be aborted.
    """
    catalog_token = _get_catalog_token(token)
    if not catalog_token:
        return None, render(request, 'products/catalog_invalid.html', status=403)
    if not _catalog_is_authenticated(request, catalog_token):
        return None, redirect('products:catalog', token=token)
    if not catalog_token.user_id:
        return None, render(request, 'products/catalog_invalid.html', {
            'message': "Cet accès n'est lié à aucun utilisateur système. Demandez à l'administrateur de recréer l'accès."
        }, status=403)
    return catalog_token, None


def catalog_my_sales(request, token):
    """Render the user's own sales list (HTML shell, JS loads via API)."""
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return err
    return render(request, 'products/catalog_my_sales.html', {
        'token': token,
        'catalog_name': catalog_token.name,
    })


def catalog_my_sales_api(request, token):
    """JSON API for the catalog user's own sales."""
    from sales.models import SaleInvoice
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        if isinstance(err, JsonResponse):
            return err
        return JsonResponse({'error': 'Authentification requise'}, status=401)

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    page = int(request.GET.get('page', 1))
    per_page = min(int(request.GET.get('per_page', 20)), 50)

    qs = SaleInvoice.objects.filter(
        seller=catalog_token.user,
        is_deleted=False,
    ).select_related('client', 'payment_method').prefetch_related('delivery')

    if q:
        qs = qs.filter(
            Q(reference__icontains=q) |
            Q(client__first_name__icontains=q) |
            Q(client__last_name__icontains=q) |
            Q(client__phone__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    qs = qs.order_by('-date', '-created_at')

    total = qs.count()
    start = (page - 1) * per_page
    invoices = qs[start:start + per_page]

    results = []
    for inv in invoices:
        client_name = ''
        if inv.client:
            client_name = inv.client.full_name if hasattr(inv.client, 'full_name') else str(inv.client)
        else:
            client_name = 'Vente anonyme'
        delivery_ref = ''
        try:
            delivery_ref = inv.delivery.reference if inv.delivery else ''
        except Exception:
            delivery_ref = ''
        results.append({
            'id': inv.id,
            'reference': inv.reference,
            'date': inv.date.strftime('%Y-%m-%d') if inv.date else '',
            'client': client_name,
            'status': inv.status,
            'status_display': inv.get_status_display(),
            'total_amount': str(inv.total_amount or 0),
            'amount_paid': str(inv.amount_paid or 0),
            'balance_due': str(inv.balance_due or 0),
            'delivery_method': inv.get_delivery_method_type_display() if inv.delivery_method_type else '',
            'delivery_status': inv.delivery_status,
            'delivery_reference': delivery_ref,
        })

    pages = (total + per_page - 1) // per_page
    # Stats
    from django.db.models import Sum
    stats = SaleInvoice.objects.filter(
        seller=catalog_token.user, is_deleted=False
    ).aggregate(
        total_sales=Sum('total_amount'),
        total_paid=Sum('amount_paid'),
        total_due=Sum('balance_due'),
    )
    return JsonResponse({
        'invoices': results,
        'total': total,
        'page': page,
        'pages': pages,
        'has_next': page < pages,
        'stats': {
            'count': SaleInvoice.objects.filter(seller=catalog_token.user, is_deleted=False).count(),
            'total_sales': str(stats['total_sales'] or 0),
            'total_paid': str(stats['total_paid'] or 0),
            'total_due': str(stats['total_due'] or 0),
        }
    })


def catalog_my_deliveries(request, token):
    """Render the user's own deliveries list."""
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return err
    from sales.models import Delivery
    return render(request, 'products/catalog_my_deliveries.html', {
        'token': token,
        'catalog_name': catalog_token.name,
        'status_choices': Delivery.Status.choices,
    })


def catalog_my_deliveries_api(request, token):
    """JSON API for the catalog user's own deliveries (via invoice.seller)."""
    from sales.models import Delivery
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        if isinstance(err, JsonResponse):
            return err
        return JsonResponse({'error': 'Authentification requise'}, status=401)

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    page = int(request.GET.get('page', 1))
    per_page = min(int(request.GET.get('per_page', 20)), 50)

    qs = Delivery.objects.filter(
        invoice__seller=catalog_token.user,
        invoice__is_deleted=False,
    ).select_related('invoice', 'carrier')

    if q:
        qs = qs.filter(
            Q(reference__icontains=q) |
            Q(tracking_number__icontains=q) |
            Q(client_name__icontains=q) |
            Q(invoice__reference__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by('-created_at')

    total = qs.count()
    start = (page - 1) * per_page
    deliveries = qs[start:start + per_page]

    results = []
    for d in deliveries:
        results.append({
            'id': d.id,
            'reference': d.reference,
            'invoice_reference': d.invoice.reference if d.invoice else '',
            'client_name': d.client_name,
            'client_phone': d.client_phone,
            'carrier': d.carrier.name if d.carrier else '',
            'tracking_number': d.tracking_number,
            'status': d.status,
            'status_display': d.get_status_display(),
            'delivery_method': d.get_delivery_method_type_display(),
            'total_amount': str(d.total_amount or 0),
            'current_position': d.current_position,
            'destination': d.destination,
            'created_at': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else '',
        })

    pages = (total + per_page - 1) // per_page
    return JsonResponse({
        'deliveries': results,
        'total': total,
        'page': page,
        'pages': pages,
        'has_next': page < pages,
    })


def catalog_my_circulation(request, token):
    """Render the catalog user's own circulation (produits en circulation)."""
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return err
    from sales.models import ProductCirculation
    return render(request, 'products/catalog_my_circulation.html', {
        'token': token,
        'catalog_name': catalog_token.name,
        'status_choices': ProductCirculation.Status.choices,
    })


def catalog_my_circulation_api(request, token):
    """JSON API for the catalog user's own circulation rows (seller = user)."""
    from sales.models import ProductCirculation
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        if isinstance(err, JsonResponse):
            return err
        return JsonResponse({'error': 'Authentification requise'}, status=401)

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    page = int(request.GET.get('page', 1))
    per_page = min(int(request.GET.get('per_page', 20)), 50)

    base = ProductCirculation.objects.filter(seller=catalog_token.user)

    # Status summary (currently out / sold / returned) over this seller's rows
    from django.db.models import Count
    summary = dict(base.values('status').annotate(n=Count('id')).values_list('status', 'n'))

    qs = base.select_related('product', 'invoice').prefetch_related('product__images')
    if q:
        qs = qs.filter(
            Q(product__reference__icontains=q) |
            Q(product__name__icontains=q) |
            Q(product__barcode__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    qs = qs.order_by('-date_out')

    total = qs.count()
    start = (page - 1) * per_page
    rows = qs[start:start + per_page]

    results = []
    for c in rows:
        p = c.product
        img = None
        if p:
            if p.main_image:
                img = p.main_image.url
            else:
                for im in p.images.all():
                    if im.image:
                        img = im.image.url
                        break
        results.append({
            'id': c.id,
            'product_reference': p.reference if p else '',
            'product_name': p.name if p else '',
            'selling_price': str(p.selling_price or 0) if p else '0',
            'image_url': img,
            'status': c.status,
            'status_display': c.get_status_display(),
            'date_out': c.date_out.strftime('%d/%m/%Y') if c.date_out else '',
            'date_back': c.date_back.strftime('%d/%m/%Y') if c.date_back else '',
            'invoice_reference': c.invoice.reference if c.invoice else '',
        })

    pages = (total + per_page - 1) // per_page
    return JsonResponse({
        'circulations': results,
        'summary': {
            'out': summary.get('out', 0),
            'sold': summary.get('sold', 0),
            'returned': summary.get('returned', 0),
        },
        'total': total,
        'page': page,
        'pages': pages,
        'has_next': page < pages,
    })


# ---------------------------------------------------------------------------
# Catalogue: client deposits (dépôts) managed by the logged-in seller.
# A seller is the "Responsable" (DepositAccount.managed_by) of the accounts
# they see here; creating one makes them the Responsable.
# ---------------------------------------------------------------------------

def _catalog_deposits_error(err):
    """Return an appropriate error response for the deposit APIs."""
    if isinstance(err, JsonResponse):
        return err
    return JsonResponse({'error': 'Authentification requise'}, status=401)


def catalog_my_deposits(request, token):
    """Render the seller's own client-deposit accounts."""
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return err
    from settings_app.models import PaymentMethod
    payment_methods = list(PaymentMethod.objects.filter(is_active=True).values('id', 'name'))
    return render(request, 'products/catalog_my_deposits.html', {
        'token': token,
        'catalog_name': catalog_token.name,
        'payment_methods': payment_methods,
    })


def catalog_my_deposits_api(request, token):
    """List the deposit accounts where the seller is the Responsable."""
    from deposits.models import DepositAccount
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return _catalog_deposits_error(err)

    q = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))
    per_page = min(int(request.GET.get('per_page', 20)), 50)

    qs = (DepositAccount.objects
          .filter(managed_by=catalog_token.user)
          .select_related('client')
          .annotate(bal=Sum('transactions__amount')))
    if q:
        qs = qs.filter(
            Q(client__first_name__icontains=q) |
            Q(client__last_name__icontains=q) |
            Q(client__phone__icontains=q) |
            Q(client__code__icontains=q)
        )
    qs = qs.order_by('client__last_name', 'client__first_name')

    total = qs.count()
    total_balance = sum((a.bal or Decimal('0')) for a in DepositAccount.objects
                        .filter(managed_by=catalog_token.user)
                        .annotate(bal=Sum('transactions__amount')))
    start = (page - 1) * per_page
    rows = qs[start:start + per_page]

    results = []
    for a in rows:
        results.append({
            'id': a.id,
            'client_name': a.client.full_name if a.client else '—',
            'client_phone': a.client.phone if a.client else '',
            'balance': str(a.bal or 0),
            'is_active': a.is_active,
            'tx_count': a.transaction_count,
        })

    pages = (total + per_page - 1) // per_page
    return JsonResponse({
        'deposits': results,
        'summary': {'count': total, 'total_balance': str(total_balance)},
        'total': total,
        'page': page,
        'pages': pages,
        'has_next': page < pages,
    })


def catalog_deposit_detail_api(request, token, account_id):
    """Transactions history of one of the seller's deposit accounts."""
    from deposits.models import DepositAccount
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return _catalog_deposits_error(err)
    try:
        account = DepositAccount.objects.select_related('client').get(pk=account_id)
    except DepositAccount.DoesNotExist:
        return JsonResponse({'error': 'Compte introuvable.'}, status=404)
    if account.managed_by_id != catalog_token.user_id:
        return JsonResponse({'error': 'Accès refusé.'}, status=403)

    txs = []
    for t in account.transactions.select_related('payment_method').order_by('-date', '-created_at'):
        txs.append({
            'type': t.transaction_type,
            'type_display': t.get_transaction_type_display(),
            'amount': str(t.amount),
            'date': t.date.strftime('%d/%m/%Y') if t.date else '',
            'payment_method': t.payment_method.name if t.payment_method else '',
            'reference': t.payment_reference,
            'description': t.description,
        })
    return JsonResponse({
        'account': {
            'id': account.id,
            'client_name': account.client.full_name if account.client else '—',
            'client_phone': account.client.phone if account.client else '',
            'balance': str(account.balance),
            'is_active': account.is_active,
        },
        'transactions': txs,
    })


def catalog_clients_search(request, token):
    """Search existing clients for the deposit-create picker."""
    from clients.models import Client
    from deposits.models import DepositAccount
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return _catalog_deposits_error(err)
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'clients': []})
    with_deposit = set(DepositAccount.objects.values_list('client_id', flat=True))
    qs = Client.objects.filter(is_active=True).filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) |
        Q(phone__icontains=q) | Q(code__icontains=q)
    ).order_by('last_name', 'first_name')[:15]
    results = [{
        'id': c.id,
        'name': c.full_name,
        'phone': c.phone,
        'has_deposit': c.id in with_deposit,
    } for c in qs]
    return JsonResponse({'clients': results})


def catalog_deposit_create(request, token):
    """Create a new deposit account (Responsable = seller) with an initial dépôt."""
    from django.db import transaction as db_transaction
    from clients.models import Client
    from deposits.models import DepositAccount, DepositTransaction
    from settings_app.models import PaymentMethod
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return _catalog_deposits_error(err)
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée.'}, status=405)

    client_id = (request.POST.get('client_id') or '').strip()
    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    amount_raw = (request.POST.get('amount') or '0').strip()
    pm_id = request.POST.get('payment_method')
    pay_ref = (request.POST.get('payment_reference') or '').strip()

    try:
        amount = Decimal(amount_raw.replace(',', '.')) if amount_raw else Decimal('0')
    except InvalidOperation:
        return JsonResponse({'error': 'Montant invalide.'}, status=400)
    if amount < 0:
        return JsonResponse({'error': 'Le montant doit être positif.'}, status=400)

    # Resolve or create the client
    if client_id:
        try:
            client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            return JsonResponse({'error': 'Client introuvable.'}, status=404)
    else:
        if not (first_name and last_name and phone):
            return JsonResponse({'error': 'Nom, prénom et téléphone du client sont requis.'}, status=400)
        client = Client.objects.create(first_name=first_name, last_name=last_name, phone=phone)

    if DepositAccount.objects.filter(client=client).exists():
        return JsonResponse({'error': f'{client.full_name} a déjà un compte dépôt.'}, status=400)

    pm = None
    if pm_id:
        try:
            pm = PaymentMethod.objects.get(pk=pm_id)
        except (PaymentMethod.DoesNotExist, ValueError):
            pm = None

    with db_transaction.atomic():
        account = DepositAccount.objects.create(
            client=client,
            managed_by=catalog_token.user,
            created_by=catalog_token.user,
        )
        if amount > 0:
            DepositTransaction.objects.create(
                account=account,
                transaction_type=DepositTransaction.TransactionType.DEPOSIT,
                amount=amount,
                payment_method=pm,
                payment_reference=pay_ref,
                description='Dépôt initial',
                created_by=catalog_token.user,
            )
    return JsonResponse({'ok': True, 'account_id': account.id})


def catalog_deposit_add_fund(request, token, account_id):
    """Record a dépôt (funds in) on one of the seller's own accounts."""
    from deposits.models import DepositAccount, DepositTransaction
    from settings_app.models import PaymentMethod
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        return _catalog_deposits_error(err)
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée.'}, status=405)
    try:
        account = DepositAccount.objects.get(pk=account_id)
    except DepositAccount.DoesNotExist:
        return JsonResponse({'error': 'Compte introuvable.'}, status=404)
    if account.managed_by_id != catalog_token.user_id:
        return JsonResponse({'error': 'Accès refusé.'}, status=403)

    amount_raw = (request.POST.get('amount') or '0').strip()
    pm_id = request.POST.get('payment_method')
    pay_ref = (request.POST.get('payment_reference') or '').strip()
    try:
        amount = Decimal(amount_raw.replace(',', '.'))
    except InvalidOperation:
        return JsonResponse({'error': 'Montant invalide.'}, status=400)
    if amount <= 0:
        return JsonResponse({'error': 'Le montant doit être positif.'}, status=400)

    pm = None
    if pm_id:
        try:
            pm = PaymentMethod.objects.get(pk=pm_id)
        except (PaymentMethod.DoesNotExist, ValueError):
            pm = None

    DepositTransaction.objects.create(
        account=account,
        transaction_type=DepositTransaction.TransactionType.DEPOSIT,
        amount=amount,
        payment_method=pm,
        payment_reference=pay_ref,
        description='Dépôt de fonds',
        created_by=catalog_token.user,
    )
    return JsonResponse({'ok': True, 'balance': str(account.balance)})


def catalog_delivery_images(request, token, delivery_id):
    """Return the InvoicePhotos attached to the sale of a given delivery."""
    from sales.models import Delivery
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        if isinstance(err, JsonResponse):
            return err
        return JsonResponse({'error': 'Authentification requise'}, status=401)

    try:
        delivery = Delivery.objects.select_related('invoice').get(
            id=delivery_id,
            invoice__seller=catalog_token.user,
            invoice__is_deleted=False,
        )
    except Delivery.DoesNotExist:
        return JsonResponse({'error': 'Livraison introuvable'}, status=404)

    photos = delivery.invoice.photos.all().order_by('uploaded_at')
    results = []
    for ph in photos:
        if not ph.image:
            continue
        results.append({
            'id': ph.id,
            'url': ph.image.url,
            'type': ph.photo_type,
            'type_display': ph.get_photo_type_display(),
            'caption': ph.caption or '',
            'uploaded_at': ph.uploaded_at.strftime('%Y-%m-%d %H:%M') if ph.uploaded_at else '',
        })
    return JsonResponse({
        'delivery_reference': delivery.reference,
        'invoice_reference': delivery.invoice.reference,
        'photos': results,
        'count': len(results),
    })


def catalog_update_delivery_status(request, token, delivery_id):
    """Allow catalog user to update status of one of their own deliveries."""
    from sales.models import Delivery
    if request.method != 'POST':
        return JsonResponse({'error': 'POST requis'}, status=405)
    catalog_token, err = _catalog_require_user(request, token)
    if err:
        if isinstance(err, JsonResponse):
            return err
        return JsonResponse({'error': 'Authentification requise'}, status=401)

    new_status = request.POST.get('status', '').strip()
    valid = {choice[0] for choice in Delivery.Status.choices}
    if new_status not in valid:
        return JsonResponse({'error': 'Statut invalide'}, status=400)

    try:
        delivery = Delivery.objects.select_related('invoice').get(
            id=delivery_id,
            invoice__seller=catalog_token.user,
            invoice__is_deleted=False,
        )
    except Delivery.DoesNotExist:
        return JsonResponse({'error': 'Livraison introuvable'}, status=404)

    delivery.status = new_status
    delivery.save(update_fields=['status', 'updated_at'])
    return JsonResponse({
        'ok': True,
        'status': delivery.status,
        'status_display': delivery.get_status_display(),
    })


def _validate_catalog_password(password):
    """Returns error message string or None."""
    if not password:
        return 'Le mot de passe est requis.'
    if len(password) < 12:
        return 'Le mot de passe doit contenir au moins 12 caractères.'
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)
    if not (has_upper and has_lower and has_digit and has_symbol):
        return 'Le mot de passe doit contenir majuscules, minuscules, chiffres et symboles.'
    return None


@login_required(login_url='login')
def catalog_manage(request):
    """Manage catalog access (pick a system user, give them a password)."""
    from .models import CatalogToken
    from users.models import User

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            user_id = request.POST.get('user_id')
            password = request.POST.get('password', '')
            if not user_id:
                messages.error(request, 'Veuillez choisir un utilisateur.')
                return redirect('products:catalog_manage')
            try:
                sys_user = User.objects.get(id=user_id, is_active=True)
            except User.DoesNotExist:
                messages.error(request, 'Utilisateur introuvable.')
                return redirect('products:catalog_manage')
            if CatalogToken.objects.filter(user=sys_user).exists():
                messages.error(request, f'"{sys_user.get_full_name() or sys_user.username}" a déjà un accès catalogue.')
            else:
                err = _validate_catalog_password(password)
                if err:
                    messages.error(request, err)
                else:
                    ct = CatalogToken(user=sys_user, created_by=request.user)
                    ct.set_password(password)
                    ct.save()
                    messages.success(request, f'Accès créé pour "{ct.name}".')

        elif action == 'change_password':
            token_id = request.POST.get('token_id')
            password = request.POST.get('password', '')
            err = _validate_catalog_password(password)
            if err:
                messages.error(request, err)
            else:
                try:
                    ct = CatalogToken.objects.get(id=token_id)
                    ct.set_password(password)
                    ct.save(update_fields=['password_hash'])
                    messages.success(request, f'Mot de passe mis à jour pour "{ct.name}".')
                except CatalogToken.DoesNotExist:
                    messages.error(request, 'Utilisateur introuvable.')

        elif action == 'toggle':
            token_id = request.POST.get('token_id')
            try:
                ct = CatalogToken.objects.get(id=token_id)
                ct.is_active = not ct.is_active
                ct.save(update_fields=['is_active'])
                status = 'activé' if ct.is_active else 'désactivé'
                messages.success(request, f'"{ct.name}" {status}.')
            except CatalogToken.DoesNotExist:
                messages.error(request, 'Utilisateur introuvable.')

        elif action == 'delete':
            token_id = request.POST.get('token_id')
            try:
                ct = CatalogToken.objects.get(id=token_id)
                ct.delete()
                messages.success(request, f'"{ct.name}" supprimé.')
            except CatalogToken.DoesNotExist:
                messages.error(request, 'Utilisateur introuvable.')

        return redirect('products:catalog_manage')

    tokens = list(CatalogToken.objects.select_related('user').order_by('-created_at'))
    used_user_ids = [ct.user_id for ct in tokens if ct.user_id]

    # Circulation linked to each account (as seller): products currently OUT,
    # plus an all-time count of items that sold while out with them.
    from sales.models import ProductCirculation
    from django.db.models import Count
    out_map = {}
    out_qs = (ProductCirculation.objects
              .filter(status=ProductCirculation.Status.OUT, seller_id__in=used_user_ids)
              .select_related('product')
              .order_by('-date_out'))
    for c in out_qs:
        out_map.setdefault(c.seller_id, []).append(c)
    sold_counts = dict(
        ProductCirculation.objects
        .filter(status=ProductCirculation.Status.SOLD, seller_id__in=used_user_ids)
        .values('seller_id')
        .annotate(n=Count('id'))
        .values_list('seller_id', 'n')
    )
    for ct in tokens:
        ct.out_circulations = out_map.get(ct.user_id, [])
        ct.out_count = len(ct.out_circulations)
        ct.sold_count = sold_counts.get(ct.user_id, 0)

    available_users = User.objects.filter(is_active=True).exclude(id__in=used_user_ids).order_by('first_name', 'last_name', 'username')
    context = {
        'tokens': tokens,
        'available_users': available_users,
    }
    return render(request, 'products/catalog_manage.html', context)


@login_required(login_url='login')
def catalog_access_logs(request):
    """Show recent catalog accesses (who accessed when from which IP)."""
    from .models import CatalogAccessLog
    logs = CatalogAccessLog.objects.select_related('token').order_by('-accessed_at')[:200]
    return render(request, 'products/catalog_access_logs.html', {'logs': logs})


# ============================================================================
# Contrôle d'inventaire (physical stock-count sessions)
# ============================================================================

def _resolve_product_by_code(code):
    """Resolve a scanned/typed code to a Product (barcode -> reference -> rfid
    -> digits-only barcode -> unique contains). Returns Product or None."""
    import re
    code = (code or '').strip()
    if not code:
        return None
    for q in (Q(barcode__iexact=code), Q(reference__iexact=code), Q(rfid_tag__iexact=code)):
        p = Product.objects.filter(q).first()
        if p:
            return p
    digits = re.sub(r'\D', '', code)
    if digits and digits != code:
        p = Product.objects.filter(barcode__iexact=digits).first()
        if p:
            return p
    cands = list(Product.objects.filter(Q(barcode__icontains=code) | Q(reference__icontains=code))[:2])
    if len(cands) == 1:
        return cands[0]
    return None


def _stock_count_report(session):
    """
    Reconcile a session. Scope depends on session.mode:
      * FULL          -> expected = all available products.
      * BLOCK_CHECK   -> expected = available members of the selected bloc(s);
                         scanned items that belong to no bloc are absorbed into
                         a single-bloc check, items of another bloc are 'hors bloc'.
      * BLOCK_DEFINE  -> the scan becomes the bloc; report shows what was set.
    """
    scans = session.scans.select_related('product').all()
    scanned_products = {}   # product_id -> product
    unknown_codes = []
    for s in scans:
        if s.product_id:
            scanned_products[s.product_id] = s.product
        else:
            unknown_codes.append(s.code)

    scanned_ids = set(scanned_products.keys())
    avail_scanned = {pid: p for pid, p in scanned_products.items() if p.status == 'available'}
    anomalies = [p for p in scanned_products.values() if p.status != 'available']

    block_qs = list(session.blocks.all())
    block_ids = [b.id for b in block_qs]
    is_block = session.mode in (
        StockCountSession.Mode.BLOCK_CHECK, StockCountSession.Mode.BLOCK_DEFINE
    ) and bool(block_ids)

    report = {
        'mode': session.mode,
        'mode_display': session.get_mode_display(),
        'blocks': block_qs,
        'anomalies': anomalies,
        'unknown_codes': unknown_codes,
        'hors_bloc': [],
        'absorbed': [],
        'scanned_total': len(scanned_products),
    }

    if not is_block:
        expected_qs = Product.objects.filter(status='available')
        missing = (list(expected_qs.exclude(id__in=scanned_ids).select_related('category'))
                   if scanned_ids else list(expected_qs.select_related('category')))
        report.update({
            'missing': missing,
            'counted_ok': list(avail_scanned.values()),
            'expected_total': expected_qs.count(),
        })
    else:
        raw_member_ids = set(Product.objects.filter(blocks__id__in=block_ids).values_list('id', flat=True))
        absorbed_ids = set(session.absorbed_products.values_list('id', flat=True))

        if session.mode == StockCountSession.Mode.BLOCK_DEFINE:
            # The scan defines the bloc; no 'missing' concept.
            report.update({
                'missing': [],
                'counted_ok': list(avail_scanned.values()),
                'expected_total': len(raw_member_ids),
                'define_set_count': len(avail_scanned),
            })
        else:
            # BLOCK_CHECK: original members = current members minus anything absorbed
            # this session (so absorbed items still show as 'ajoutés', not members).
            original_member_ids = raw_member_ids - absorbed_ids
            expected_ids = set(Product.objects.filter(
                id__in=original_member_ids, status='available'
            ).values_list('id', flat=True))
            missing_ids = expected_ids - scanned_ids
            missing = list(Product.objects.filter(id__in=missing_ids).select_related('category'))
            counted_ok = [p for pid, p in avail_scanned.items() if pid in expected_ids]

            off = [(pid, p) for pid, p in avail_scanned.items() if pid not in original_member_ids]
            if absorbed_ids:
                # Closed session: absorbed already recorded.
                report['absorbed'] = [p for pid, p in off if pid in absorbed_ids]
                report['hors_bloc'] = [p for pid, p in off if pid not in absorbed_ids]
            elif len(block_ids) == 1:
                # Open preview (or a check that absorbed nothing): items in NO bloc
                # would be absorbed; items in another bloc are hors bloc.
                any_block_ids = set(Product.objects.filter(
                    id__in=[pid for pid, _ in off], blocks__isnull=False
                ).values_list('id', flat=True))
                report['absorbed'] = [p for pid, p in off if pid not in any_block_ids]
                report['hors_bloc'] = [p for pid, p in off if pid in any_block_ids]
            else:
                report['hors_bloc'] = [p for _, p in off]

            report.update({
                'missing': missing,
                'counted_ok': counted_ok,
                'expected_total': len(expected_ids),
            })

    report.update({
        'missing_count': len(report['missing']),
        'anomaly_count': len(anomalies),
        'hors_bloc_count': len(report['hors_bloc']),
        'absorbed_count': len(report['absorbed']),
    })
    return report


@login_required(login_url='login')
def stock_count_list(request):
    sessions = StockCountSession.objects.select_related('started_by').prefetch_related('blocks').all()[:100]
    open_session = StockCountSession.objects.filter(status='open').order_by('-started_at').first()
    blocks = ProductBlock.objects.filter(is_active=True).order_by('name')
    return render(request, 'products/stock_count_list.html', {
        'sessions': sessions, 'open_session': open_session, 'blocks': blocks,
    })


@login_required(login_url='login')
@require_http_methods(["POST"])
def stock_count_start(request):
    # Only one open session at a time: resume it if present.
    existing = StockCountSession.objects.filter(status='open').order_by('-started_at').first()
    if existing:
        return redirect('products:stock_count_detail', pk=existing.pk)

    mode = request.POST.get('mode') or StockCountSession.Mode.FULL
    if mode not in dict(StockCountSession.Mode.choices):
        mode = StockCountSession.Mode.FULL
    block_ids = [int(b) for b in request.POST.getlist('block_ids') if str(b).isdigit()]

    if mode == StockCountSession.Mode.BLOCK_DEFINE and len(block_ids) != 1:
        messages.error(request, 'Choisissez exactement un bloc à définir.')
        return redirect('products:stock_count_list')
    if mode == StockCountSession.Mode.BLOCK_CHECK and not block_ids:
        messages.error(request, 'Choisissez au moins un bloc à contrôler.')
        return redirect('products:stock_count_list')

    session = StockCountSession.objects.create(started_by=request.user, mode=mode)
    if mode in (StockCountSession.Mode.BLOCK_CHECK, StockCountSession.Mode.BLOCK_DEFINE) and block_ids:
        session.blocks.set(ProductBlock.objects.filter(id__in=block_ids, is_active=True))
    return redirect('products:stock_count_detail', pk=session.pk)


@login_required(login_url='login')
def stock_count_detail(request, pk):
    session = get_object_or_404(StockCountSession, pk=pk)
    context = {'session': session}
    if session.status == 'open':
        context['scans'] = session.scans.select_related('product').all()[:500]
        context['scanned_count'] = session.scans.filter(product__isnull=False).values('product').distinct().count()
    else:
        context['report'] = _stock_count_report(session)
        context['blocks'] = ProductBlock.objects.filter(is_active=True).order_by('name')
    return render(request, 'products/stock_count_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def stock_count_apply_block(request, pk):
    """Pour a finished session's scanned (available) products into a bloc.
    action='replace' re-baselines the bloc; 'add' appends."""
    session = get_object_or_404(StockCountSession, pk=pk)
    action = request.POST.get('apply_action', 'add')
    try:
        block = ProductBlock.objects.get(pk=request.POST.get('block_id'), is_active=True)
    except (ProductBlock.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Bloc introuvable.')
        return redirect('products:stock_count_detail', pk=pk)

    scanned_avail_ids = list(
        session.scans.filter(product__status='available')
        .values_list('product_id', flat=True).distinct()
    )
    if action == 'replace':
        block.products.set(Product.objects.filter(id__in=scanned_avail_ids))
        messages.success(request, f'Bloc « {block.name} » réinitialisé avec {len(scanned_avail_ids)} produit(s) scanné(s).')
    else:
        if scanned_avail_ids:
            block.products.add(*scanned_avail_ids)
        messages.success(request, f'{len(scanned_avail_ids)} produit(s) scanné(s) ajouté(s) au bloc « {block.name} ».')
    return redirect('products:stock_count_detail', pk=pk)


@login_required(login_url='login')
@require_http_methods(["POST"])
def stock_count_scan(request, pk):
    import json as _json
    session = get_object_or_404(StockCountSession, pk=pk)
    if session.status != 'open':
        return JsonResponse({'ok': False, 'error': 'Session terminée.'}, status=409)
    try:
        data = _json.loads(request.body or '{}')
    except ValueError:
        data = {}
    code = (data.get('code') or '').strip()
    if not code:
        return JsonResponse({'ok': False, 'error': 'Code vide.'}, status=400)

    product = _resolve_product_by_code(code)
    if product:
        already = session.scans.filter(product=product).exists()
        if already:
            result = 'duplicate'
        else:
            StockCountScan.objects.create(session=session, product=product, code=code)
            result = 'counted'
        payload = {
            'ok': True, 'result': result,
            'product': {'reference': product.reference, 'name': product.name or '',
                        'status': product.get_status_display(), 'is_available': product.status == 'available'},
        }
    else:
        StockCountScan.objects.create(session=session, product=None, code=code)
        payload = {'ok': True, 'result': 'unknown', 'code': code}

    payload['scanned_count'] = session.scans.filter(product__isnull=False).values('product').distinct().count()
    return JsonResponse(payload)


@login_required(login_url='login')
@require_http_methods(["POST"])
def stock_count_finish(request, pk):
    from django.utils import timezone as _tz
    session = get_object_or_404(StockCountSession, pk=pk)
    if session.status == 'open':
        # Apply bloc membership changes before closing.
        scanned_avail_ids = set(
            session.scans.filter(product__status='available')
            .values_list('product_id', flat=True)
        )
        if session.mode == StockCountSession.Mode.BLOCK_DEFINE:
            block = session.blocks.first()
            if block:
                # Re-baseline: the bloc becomes exactly the scanned available products.
                block.products.set(Product.objects.filter(id__in=scanned_avail_ids))
        elif session.mode == StockCountSession.Mode.BLOCK_CHECK and session.blocks.count() == 1:
            block = session.blocks.first()
            member_ids = set(block.products.values_list('id', flat=True))
            any_block_ids = set(
                Product.objects.filter(id__in=scanned_avail_ids, blocks__isnull=False)
                .values_list('id', flat=True)
            )
            # Absorb scanned items that belong to NO bloc yet (newly-added stock).
            to_absorb = [pid for pid in scanned_avail_ids
                         if pid not in any_block_ids and pid not in member_ids]
            if to_absorb:
                block.products.add(*to_absorb)
                session.absorbed_products.add(*to_absorb)

        session.status = 'closed'
        session.finished_at = _tz.now()
        session.save(update_fields=['status', 'finished_at'])
        ActivityLog.objects.create(
            user=request.user, action=ActivityLog.ActionType.UPDATE,
            model_name='StockCountSession', object_id=str(session.id),
            object_repr=f'Inventaire #{session.id} terminé',
        )
    return redirect('products:stock_count_detail', pk=session.pk)


# ---------------------------------------------------------------------------
# Blocs (zones) management
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def block_list(request):
    blocks = ProductBlock.objects.annotate(
        n_products=Count('products', distinct=True)
    ).order_by('-is_active', 'name')
    return render(request, 'products/block_list.html', {'blocks': blocks})


@login_required(login_url='login')
@require_http_methods(["POST"])
def block_create(request):
    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, 'Nom du bloc requis.')
    elif ProductBlock.objects.filter(name__iexact=name).exists():
        messages.error(request, f'Le bloc « {name} » existe déjà.')
    else:
        ProductBlock.objects.create(name=name, created_by=request.user)
        messages.success(request, f'Bloc « {name} » créé.')
    return redirect('products:block_list')


@login_required(login_url='login')
@require_http_methods(["POST"])
def block_update(request, pk):
    block = get_object_or_404(ProductBlock, pk=pk)
    action = request.POST.get('action')
    if action == 'rename':
        name = (request.POST.get('name') or '').strip()
        if not name:
            messages.error(request, 'Nom requis.')
        elif ProductBlock.objects.filter(name__iexact=name).exclude(pk=block.pk).exists():
            messages.error(request, f'Le bloc « {name} » existe déjà.')
        else:
            block.name = name
            block.save(update_fields=['name', 'updated_at'])
            messages.success(request, 'Bloc renommé.')
    elif action == 'toggle':
        block.is_active = not block.is_active
        block.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, 'Bloc ' + ('activé.' if block.is_active else 'désactivé.'))
    elif action == 'delete':
        block.delete()
        messages.success(request, 'Bloc supprimé.')
    return redirect('products:block_list')


@login_required(login_url='login')
def block_detail(request, pk):
    block = get_object_or_404(ProductBlock, pk=pk)
    if request.method == 'POST' and request.POST.get('action') == 'remove_product':
        pid = request.POST.get('product_id')
        if pid:
            block.products.remove(pid)
            messages.success(request, 'Produit retiré du bloc.')
        return redirect('products:block_detail', pk=pk)
    products = block.products.select_related('category').order_by('reference')
    return render(request, 'products/block_detail.html', {'bloc': block, 'products': products})


@login_required(login_url='login')
@require_http_methods(["POST"])
def block_bulk_assign(request):
    """Assign selected products (from the product list) to a bloc."""
    block_id = request.POST.get('block_id')
    product_ids = [int(p) for p in request.POST.getlist('product_ids') if str(p).isdigit()]
    if not block_id or not product_ids:
        return JsonResponse({'ok': False, 'error': 'Bloc et produits requis.'}, status=400)
    try:
        block = ProductBlock.objects.get(pk=block_id, is_active=True)
    except ProductBlock.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Bloc introuvable.'}, status=404)
    block.products.add(*product_ids)
    return JsonResponse({'ok': True, 'assigned': len(product_ids), 'block': block.name})


@login_required(login_url='login')
def stock_count_report_print(request, pk):
    from django.utils import timezone as _tz
    session = get_object_or_404(StockCountSession, pk=pk)
    return render(request, 'products/stock_count_report_print.html', {
        'session': session, 'report': _stock_count_report(session),
        'now': _tz.now(), 'user': request.user,
    })
