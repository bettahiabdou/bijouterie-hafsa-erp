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
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import Product, ProductImage, ProductStone
from .print_utils import print_product_label, print_price_tag, print_test_label, generate_product_label_zpl, generate_price_tag_zpl, queue_print_job
from settings_app.models import ProductCategory, MetalType, MetalPurity, BankAccount
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
            product_sizes = request.POST.getlist('product_size')

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

                    # Create product instance (don't save yet)
                    product = Product(
                        name=product_name,
                        product_type=product_product_type,
                        category_id=product_category_id,
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

    # Value calculations - only count available products
    total_value = Product.objects.filter(status='available').aggregate(
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
