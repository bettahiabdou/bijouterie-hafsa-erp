"""
Purchase management views for Bijouterie Hafsa ERP
Handles purchase orders, purchase invoices, and consignments
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Sum, Count, F, DecimalField, Value
from django.db.models.functions import Coalesce
from datetime import timedelta
from decimal import Decimal

from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseInvoiceAction,
    Consignment,
    ConsignmentItem
)
from users.models import ActivityLog


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
def purchase_order_list(request):
    """List all purchase orders with filtering"""
    orders = PurchaseOrder.objects.select_related(
        'supplier', 'approved_by', 'created_by'
    ).all()

    # Search by reference or supplier
    search = request.GET.get('search', '')
    if search:
        orders = orders.filter(
            Q(reference__icontains=search) |
            Q(supplier__name__icontains=search)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        orders = orders.filter(status=status)

    # Filter by order type
    order_type = request.GET.get('order_type', '')
    if order_type:
        orders = orders.filter(order_type=order_type)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        orders = orders.filter(date__gte=date_from)
    if date_to:
        orders = orders.filter(date__lte=date_to)

    # Statistics
    stats = {
        'total': orders.count(),
        'draft': orders.filter(status='draft').count(),
        'pending': orders.filter(status='pending').count(),
        'approved': orders.filter(status='approved').count(),
        'total_amount': orders.aggregate(
            total=Coalesce(Sum('total_amount'), Value(0), output_field=DecimalField())
        )['total']
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(orders.order_by('-date', '-created_at'), 20)
    page = request.GET.get('page', 1)
    orders_page = paginator.get_page(page)

    context = {
        'orders': orders_page,
        'search': search,
        'status': status,
        'order_type': order_type,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'status_choices': PurchaseOrder.Status.choices,
        'type_choices': PurchaseOrder.OrderType.choices,
    }
    return render(request, 'purchases/purchase_order_list.html', context)


@login_required
@permission_required('purchases.add_purchaseorder', raise_exception=True)
def purchase_order_create(request):
    """Create new purchase order"""
    if request.method == 'POST':
        # Generate reference
        from django.utils import timezone
        today = timezone.now().date()
        today_str = today.strftime('%Y%m%d')
        last_order = PurchaseOrder.objects.filter(
            reference__startswith=f'PO-{today_str}'
        ).last()

        if last_order:
            seq = int(last_order.reference.split('-')[-1]) + 1
        else:
            seq = 1

        reference = f'PO-{today_str}-{seq:04d}'

        order = PurchaseOrder.objects.create(
            reference=reference,
            date=now().date(),
            supplier_id=request.POST.get('supplier'),
            order_type=request.POST.get('order_type', 'finished'),
            client_id=request.POST.get('client') or None,
            expected_date=request.POST.get('expected_date') or None,
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.CREATE,
            model_name='PurchaseOrder',
            object_id=str(order.id),
            object_repr=f'Created purchase order {order.reference}',
            ip_address=get_client_ip(request)
        )

        return redirect('purchases:purchase_order_detail', reference=order.reference)

    from suppliers.models import Supplier
    from clients.models import Client
    context = {
        'suppliers': Supplier.objects.all(),
        'clients': Client.objects.all(),
        'type_choices': PurchaseOrder.OrderType.choices,
    }
    return render(request, 'purchases/purchase_order_form.html', context)


@login_required
def purchase_order_detail(request, reference):
    """View purchase order details"""
    order = get_object_or_404(
        PurchaseOrder.objects.select_related(
            'supplier', 'created_by', 'approved_by', 'client'
        ).prefetch_related('items'),
        reference=reference
    )

    # Log view
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.VIEW,
        model_name='PurchaseOrder',
        object_id=str(order.id),
        object_repr=f'Viewed purchase order {order.reference}',
        ip_address=get_client_ip(request)
    )

    # Handle approval
    if request.method == 'POST' and request.POST.get('action') == 'approve':
        if request.user.has_perm('purchases.change_purchaseorder'):
            order.status = 'approved'
            order.approved_by = request.user
            order.approved_at = now()
            order.save()

            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.UPDATE,
                model_name='PurchaseOrder',
                object_id=str(order.id),
                object_repr=f'Approved purchase order {order.reference}',
                ip_address=get_client_ip(request)
            )

    context = {
        'order': order,
        'items': order.items.all(),
    }
    return render(request, 'purchases/purchase_order_detail.html', context)


@login_required
def purchase_invoice_list(request):
    """List all purchase invoices with filtering"""
    invoices = PurchaseInvoice.objects.select_related(
        'supplier', 'created_by', 'purchase_order'
    ).all()

    # Search
    search = request.GET.get('search', '')
    if search:
        invoices = invoices.filter(
            Q(reference__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(supplier_invoice_ref__icontains=search)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        invoices = invoices.filter(status=status)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        invoices = invoices.filter(date__gte=date_from)
    if date_to:
        invoices = invoices.filter(date__lte=date_to)

    # Statistics
    today = now().date()
    thirty_days_ago = today - timedelta(days=30)

    stats = {
        'total': invoices.count(),
        'draft': invoices.filter(status='draft').count(),
        'unpaid': invoices.filter(balance_due__gt=0).count(),
        'total_amount': invoices.aggregate(
            total=Coalesce(Sum('total_amount'), Value(0), output_field=DecimalField())
        )['total'],
        'amount_due': invoices.filter(
            balance_due__gt=0
        ).aggregate(
            total=Coalesce(Sum('balance_due'), Value(0), output_field=DecimalField())
        )['total'],
        'overdue': invoices.filter(
            Q(balance_due__gt=0) & Q(date__lt=thirty_days_ago)
        ).count(),
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(invoices.order_by('-date', '-created_at'), 20)
    page = request.GET.get('page', 1)
    invoices_page = paginator.get_page(page)

    context = {
        'invoices': invoices_page,
        'search': search,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'status_choices': PurchaseInvoice.Status.choices,
    }
    return render(request, 'purchases/purchase_invoice_list.html', context)


@login_required
def purchase_invoice_create(request):
    """Create new purchase invoice"""
    if request.method == 'POST':
        try:
            # Generate reference
            from django.utils import timezone
            today = timezone.now().date()
            today_str = today.strftime('%Y%m%d')
            last_invoice = PurchaseInvoice.objects.filter(
                reference__startswith=f'PI-{today_str}'
            ).last()

            if last_invoice:
                seq = int(last_invoice.reference.split('-')[-1]) + 1
            else:
                seq = 1

            reference = f'PI-{today_str}-{seq:04d}'

            invoice = PurchaseInvoice.objects.create(
                reference=reference,
                date=now().date(),
                supplier_id=request.POST.get('supplier'),
                supplier_invoice_ref=request.POST.get('supplier_invoice_ref', ''),
                invoice_type=request.POST.get('invoice_type', 'finished'),
                purchase_order_id=request.POST.get('purchase_order') or None,
                notes=request.POST.get('notes', ''),
                created_by=request.user,
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.CREATE,
                model_name='PurchaseInvoice',
                object_id=str(invoice.id),
                object_repr=f'Created purchase invoice {invoice.reference}',
                ip_address=get_client_ip(request)
            )

            return redirect('purchases:purchase_invoice_detail', reference=invoice.reference)
        except Exception as e:
            messages.error(request, f'Erreur: {str(e)}')

    try:
        from suppliers.models import Supplier
        context = {
            'suppliers': Supplier.objects.all(),
            'purchase_orders': PurchaseOrder.objects.filter(status='approved'),
            'type_choices': PurchaseInvoice.InvoiceType.choices,
        }
        return render(request, 'purchases/purchase_invoice_form.html', context)
    except Exception as e:
        messages.error(request, f'Erreur: {str(e)}')
        return redirect('purchases:purchase_invoice_list')


@login_required
def purchase_invoice_detail(request, reference):
    """View purchase invoice details"""
    from products.models import Product

    invoice = get_object_or_404(
        PurchaseInvoice.objects.select_related(
            'supplier', 'created_by', 'purchase_order'
        ).prefetch_related('items', 'items__product'),
        reference=reference
    )

    # Log view
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.VIEW,
        model_name='PurchaseInvoice',
        object_id=str(invoice.id),
        object_repr=f'Viewed purchase invoice {invoice.reference}',
        ip_address=get_client_ip(request)
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        # Handle confirm action
        if action == 'confirm':
            if request.user.has_perm('purchases.change_purchaseinvoice'):
                invoice.status = 'confirmed'
                invoice.save()

                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='PurchaseInvoice',
                    object_id=str(invoice.id),
                    object_repr=f'Confirmed purchase invoice {invoice.reference}',
                    ip_address=get_client_ip(request)
                )

        # Handle add multiple products action
        elif action == 'add_products':
            product_ids_str = request.POST.get('product_ids', '')
            if product_ids_str:
                product_ids = [pid.strip() for pid in product_ids_str.split(',') if pid.strip()]
                added_count = 0
                errors = []

                for product_id in product_ids:
                    try:
                        product = Product.objects.get(id=product_id)

                        # Check if product is already linked to ANY purchase invoice
                        existing_link = PurchaseInvoiceItem.objects.filter(product=product).first()
                        if existing_link:
                            errors.append(f'{product.reference}: déjà dans facture {existing_link.invoice.reference}')
                            continue

                        # Validate required fields
                        if not product.category:
                            errors.append(f'{product.reference}: pas de catégorie')
                        elif not product.metal_type:
                            errors.append(f'{product.reference}: pas de type de métal')
                        elif not product.metal_purity:
                            errors.append(f'{product.reference}: pas de titre')
                        else:
                            # Create a new invoice item linked to this product
                            PurchaseInvoiceItem.objects.create(
                                invoice=invoice,
                                product=product,
                                description=f"{product.name} - {product.reference}",
                                category=product.category,
                                metal_type=product.metal_type,
                                metal_purity=product.metal_purity,
                                gross_weight=product.gross_weight or Decimal('0'),
                                net_weight=product.net_weight or Decimal('0'),
                                price_per_gram=product.purchase_price_per_gram or Decimal('0'),
                                labor_cost=product.labor_cost or Decimal('0'),
                            )
                            added_count += 1
                    except Product.DoesNotExist:
                        errors.append(f'ID {product_id}: non trouvé')
                    except Exception as e:
                        errors.append(f'ID {product_id}: {str(e)}')

                # Update invoice totals once after all items added
                if added_count > 0:
                    invoice.calculate_totals()
                    invoice.save()

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='PurchaseInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'Added {added_count} products to invoice {invoice.reference}',
                        ip_address=get_client_ip(request)
                    )
                    messages.success(request, f'{added_count} produit(s) ajouté(s) à la facture.')

                if errors:
                    messages.error(request, f'Erreurs: {", ".join(errors)}')

        # Handle bulk product creation (create new products and add to invoice)
        elif action == 'bulk_create_products':
            from settings_app.models import ProductCategory, MetalType, MetalPurity, BankAccount

            # Get common parameters
            purchase_price_per_gram = Decimal(request.POST.get('purchase_price_per_gram', '0') or '0')
            labor_cost = Decimal(request.POST.get('labor_cost', '0') or '0')
            stone_cost = Decimal(request.POST.get('stone_cost', '0') or '0')
            other_cost = Decimal(request.POST.get('other_cost', '0') or '0')
            margin_type = request.POST.get('margin_type', 'percentage')
            margin_value = Decimal(request.POST.get('margin_value', '25') or '25')

            # Get product data lists
            names = request.POST.getlist('product_name')
            categories_list = request.POST.getlist('product_category')
            types = request.POST.getlist('product_type')
            weights = request.POST.getlist('product_weight')
            selling_prices = request.POST.getlist('product_selling_price')
            metal_types = request.POST.getlist('product_metal_type')
            purities_list = request.POST.getlist('product_purity')
            sizes = request.POST.getlist('product_size')

            created_count = 0
            errors = []

            for i, weight in enumerate(weights):
                try:
                    net_weight = Decimal(weight or '0')
                    if net_weight <= 0:
                        continue

                    # Get optional fields
                    name = names[i] if i < len(names) else f'Produit {i+1}'
                    category_id = categories_list[i] if i < len(categories_list) else ''
                    product_type = types[i] if i < len(types) else 'finished'
                    selling_price_str = selling_prices[i] if i < len(selling_prices) else ''
                    metal_type_id = metal_types[i] if i < len(metal_types) else ''
                    purity_id = purities_list[i] if i < len(purities_list) else ''
                    size = sizes[i] if i < len(sizes) else ''

                    # Get related objects
                    category = ProductCategory.objects.filter(pk=category_id).first() if category_id else None
                    metal_type = MetalType.objects.filter(pk=metal_type_id).first() if metal_type_id else None
                    metal_purity = MetalPurity.objects.filter(pk=purity_id).first() if purity_id else None

                    # Validate required fields
                    if not category:
                        errors.append(f'Produit {i+1}: catégorie requise')
                        continue
                    if not metal_type:
                        errors.append(f'Produit {i+1}: type de métal requis')
                        continue
                    if not metal_purity:
                        errors.append(f'Produit {i+1}: pureté requise')
                        continue

                    # Calculate costs
                    metal_cost = net_weight * purchase_price_per_gram
                    total_cost = metal_cost + labor_cost + stone_cost + other_cost

                    # Calculate selling price
                    if selling_price_str:
                        selling_price = Decimal(selling_price_str)
                    else:
                        if margin_type == 'percentage':
                            selling_price = total_cost * (1 + margin_value / 100)
                        else:
                            selling_price = total_cost + margin_value

                    # Create the product
                    product = Product(
                        name=name or f'Produit {invoice.reference}',
                        category=category,
                        product_type=product_type,
                        metal_type=metal_type,
                        metal_purity=metal_purity,
                        gross_weight=net_weight,
                        net_weight=net_weight,
                        size=size,
                        supplier=invoice.supplier,
                        purchase_price_per_gram=purchase_price_per_gram,
                        labor_cost=labor_cost,
                        stone_cost=stone_cost,
                        other_cost=other_cost,
                        selling_price=selling_price,
                        status='available',
                        created_by=request.user
                    )
                    product.save()

                    # Create invoice item linked to product
                    PurchaseInvoiceItem.objects.create(
                        invoice=invoice,
                        product=product,
                        description=f"{product.name} - {product.reference}",
                        category=category,
                        metal_type=metal_type,
                        metal_purity=metal_purity,
                        gross_weight=net_weight,
                        net_weight=net_weight,
                        price_per_gram=purchase_price_per_gram,
                        labor_cost=labor_cost,
                    )

                    created_count += 1

                    # Log the creation
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.CREATE,
                        model_name='Product',
                        object_id=str(product.id),
                        object_repr=f'Created product {product.reference} from invoice {invoice.reference}',
                        ip_address=get_client_ip(request)
                    )

                except Exception as e:
                    errors.append(f'Produit {i+1}: {str(e)}')

            if created_count > 0:
                # Update invoice totals
                invoice.calculate_totals()
                invoice.save()

                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='PurchaseInvoice',
                    object_id=str(invoice.id),
                    object_repr=f'Bulk created {created_count} products for invoice {invoice.reference}',
                    ip_address=get_client_ip(request)
                )
                messages.success(request, f'{created_count} produit(s) créé(s) et ajouté(s) à la facture.')

            if errors:
                messages.error(request, f'Erreurs: {"; ".join(errors[:5])}')  # Show first 5 errors

            return redirect('purchases:purchase_invoice_detail', reference=invoice.reference)

        # Handle return item action (Retour au fournisseur)
        elif action == 'return_item':
            item_id = request.POST.get('item_id')
            notes = request.POST.get('notes', '')
            if item_id:
                try:
                    item = PurchaseInvoiceItem.objects.get(id=item_id, invoice=invoice)
                    original_product = item.product
                    original_ref = original_product.reference if original_product else item.description

                    # Create action record
                    PurchaseInvoiceAction.objects.create(
                        invoice=invoice,
                        action_type=PurchaseInvoiceAction.ActionType.RETURN,
                        original_product=original_product,
                        original_product_ref=original_ref,
                        notes=notes,
                        created_by=request.user
                    )

                    # Update product status to "returned"
                    if original_product:
                        original_product.status = 'returned'
                        original_product.save(update_fields=['status'])

                    # Delete the item from invoice
                    item.delete()
                    invoice.calculate_totals()
                    invoice.save()

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.DELETE,
                        model_name='PurchaseInvoiceItem',
                        object_id=str(item_id),
                        object_repr=f'Returned item {original_ref} to supplier',
                        ip_address=get_client_ip(request)
                    )
                    messages.success(request, f'Produit {original_ref} retourné au fournisseur.')
                except PurchaseInvoiceItem.DoesNotExist:
                    messages.error(request, 'Article non trouvé.')

        # Handle exchange item action (Échange avec fournisseur)
        elif action == 'exchange_item':
            item_id = request.POST.get('item_id')
            replacement_product_id = request.POST.get('replacement_product_id')
            notes = request.POST.get('notes', '')

            if item_id and replacement_product_id:
                try:
                    item = PurchaseInvoiceItem.objects.get(id=item_id, invoice=invoice)
                    original_product = item.product
                    original_ref = original_product.reference if original_product else item.description

                    replacement_product = Product.objects.get(id=replacement_product_id)

                    # Check if replacement is already linked
                    existing_link = PurchaseInvoiceItem.objects.filter(product=replacement_product).first()
                    if existing_link:
                        messages.error(request, f'{replacement_product.reference} est déjà dans la facture {existing_link.invoice.reference}')
                    elif not replacement_product.category or not replacement_product.metal_type or not replacement_product.metal_purity:
                        messages.error(request, f'{replacement_product.reference} n\'a pas toutes les informations requises.')
                    else:
                        # Create action record
                        PurchaseInvoiceAction.objects.create(
                            invoice=invoice,
                            action_type=PurchaseInvoiceAction.ActionType.EXCHANGE,
                            original_product=original_product,
                            original_product_ref=original_ref,
                            replacement_product=replacement_product,
                            notes=notes,
                            created_by=request.user
                        )

                        # Update original product status to "returned"
                        if original_product:
                            original_product.status = 'returned'
                            original_product.save(update_fields=['status'])

                        # Delete old item and create new one with replacement
                        item.delete()

                        PurchaseInvoiceItem.objects.create(
                            invoice=invoice,
                            product=replacement_product,
                            description=f"{replacement_product.name} - {replacement_product.reference}",
                            category=replacement_product.category,
                            metal_type=replacement_product.metal_type,
                            metal_purity=replacement_product.metal_purity,
                            gross_weight=replacement_product.gross_weight or Decimal('0'),
                            net_weight=replacement_product.net_weight or Decimal('0'),
                            price_per_gram=replacement_product.purchase_price_per_gram or Decimal('0'),
                            labor_cost=replacement_product.labor_cost or Decimal('0'),
                        )

                        invoice.calculate_totals()
                        invoice.save()

                        ActivityLog.objects.create(
                            user=request.user,
                            action=ActivityLog.ActionType.UPDATE,
                            model_name='PurchaseInvoice',
                            object_id=str(invoice.id),
                            object_repr=f'Exchanged {original_ref} for {replacement_product.reference}',
                            ip_address=get_client_ip(request)
                        )
                        messages.success(request, f'Échange effectué: {original_ref} → {replacement_product.reference}')

                except PurchaseInvoiceItem.DoesNotExist:
                    messages.error(request, 'Article non trouvé.')
                except Product.DoesNotExist:
                    messages.error(request, 'Produit de remplacement non trouvé.')

        return redirect('purchases:purchase_invoice_detail', reference=reference)

    # Get products that are NOT already linked to ANY purchase invoice
    # This ensures each product can only be in one purchase invoice
    products_in_invoices = PurchaseInvoiceItem.objects.filter(
        product__isnull=False
    ).values_list('product_id', flat=True)

    available_products = Product.objects.select_related(
        'category', 'metal_type', 'metal_purity'
    ).exclude(
        id__in=products_in_invoices
    ).order_by('-created_at')[:100]  # Limit to recent 100

    # Get items and calculate dynamic totals from linked products
    items = invoice.items.select_related('product').all()
    dynamic_subtotal = Decimal('0')
    total_gross_weight = Decimal('0')
    total_net_weight = Decimal('0')

    for item in items:
        if item.product:
            # Calculate total from current product values
            gross_weight = item.product.gross_weight or Decimal('0')
            net_weight = item.product.net_weight or Decimal('0')
            price_per_gram = item.product.purchase_price_per_gram or Decimal('0')
            labor_cost = item.product.labor_cost or Decimal('0')
            item.dynamic_total = (net_weight * price_per_gram) + labor_cost
            dynamic_subtotal += item.dynamic_total
            total_gross_weight += gross_weight
            total_net_weight += net_weight
        else:
            # Use stored values for items without linked product
            item.dynamic_total = item.total_amount
            dynamic_subtotal += item.total_amount
            total_gross_weight += item.gross_weight or Decimal('0')
            total_net_weight += item.net_weight or Decimal('0')

    # Calculate dynamic invoice totals
    dynamic_total = dynamic_subtotal - invoice.discount_amount
    dynamic_balance = dynamic_total - invoice.amount_paid

    # Get return/exchange actions history
    invoice_actions = invoice.actions.select_related(
        'original_product', 'replacement_product', 'created_by'
    ).all()

    # Get data for bulk product creation modal
    from settings_app.models import ProductCategory, MetalType, MetalPurity, BankAccount
    categories = ProductCategory.objects.filter(is_active=True)
    metals = MetalType.objects.all()
    purities = MetalPurity.objects.all()
    bank_accounts = BankAccount.objects.filter(is_active=True)
    product_types = Product.ProductType.choices

    context = {
        'invoice': invoice,
        'items': items,
        'all_products': available_products,
        'dynamic_subtotal': dynamic_subtotal,
        'dynamic_total': dynamic_total,
        'dynamic_balance': dynamic_balance,
        'total_gross_weight': total_gross_weight,
        'total_net_weight': total_net_weight,
        'invoice_actions': invoice_actions,
        # For bulk product creation
        'categories': categories,
        'metals': metals,
        'purities': purities,
        'bank_accounts': bank_accounts,
        'product_types': product_types,
    }
    return render(request, 'purchases/purchase_invoice_detail.html', context)


@login_required
def consignment_list(request):
    """List all consignments"""
    consignments = Consignment.objects.select_related(
        'supplier', 'created_by'
    ).all()

    # Search
    search = request.GET.get('search', '')
    if search:
        consignments = consignments.filter(
            Q(reference__icontains=search) |
            Q(supplier__name__icontains=search)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        consignments = consignments.filter(status=status)

    # Statistics
    stats = {
        'total': consignments.count(),
        'active': consignments.filter(status='active').count(),
        'total_value': consignments.aggregate(
            total=Coalesce(Sum('total_value'), Value(0), output_field=DecimalField())
        )['total'],
        'amount_due': consignments.aggregate(
            total=Coalesce(Sum('amount_due'), Value(0), output_field=DecimalField())
        )['total'],
    }

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(consignments.order_by('-date_received', '-created_at'), 20)
    page = request.GET.get('page', 1)
    consignments_page = paginator.get_page(page)

    context = {
        'consignments': consignments_page,
        'search': search,
        'status': status,
        'stats': stats,
        'status_choices': Consignment.Status.choices,
    }
    return render(request, 'purchases/consignment_list.html', context)


@login_required
@permission_required('purchases.add_consignment', raise_exception=True)
def consignment_create(request):
    """Create new consignment"""
    if request.method == 'POST':
        # Generate reference
        from django.utils import timezone
        today = timezone.now().date()
        today_str = today.strftime('%Y%m%d')
        last_consignment = Consignment.objects.filter(
            reference__startswith=f'CS-{today_str}'
        ).last()

        if last_consignment:
            seq = int(last_consignment.reference.split('-')[-1]) + 1
        else:
            seq = 1

        reference = f'CS-{today_str}-{seq:04d}'

        consignment = Consignment.objects.create(
            reference=reference,
            date_received=request.POST.get('date_received') or now().date(),
            supplier_id=request.POST.get('supplier'),
            return_deadline=request.POST.get('return_deadline') or None,
            commission_percent=Decimal(request.POST.get('commission_percent', 0)),
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.CREATE,
            model_name='Consignment',
            object_id=str(consignment.id),
            object_repr=f'Created consignment {consignment.reference}',
            ip_address=get_client_ip(request)
        )

        return redirect('purchases:consignment_detail', reference=consignment.reference)

    from suppliers.models import Supplier
    context = {
        'suppliers': Supplier.objects.all(),
    }
    return render(request, 'purchases/consignment_form.html', context)


@login_required
def consignment_detail(request, reference):
    """View consignment details"""
    consignment = get_object_or_404(
        Consignment.objects.select_related(
            'supplier', 'created_by'
        ).prefetch_related('items'),
        reference=reference
    )

    # Log view
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.VIEW,
        model_name='Consignment',
        object_id=str(consignment.id),
        object_repr=f'Viewed consignment {consignment.reference}',
        ip_address=get_client_ip(request)
    )

    # Calculate statistics
    items = consignment.items.all()
    stats = {
        'total_items': items.count(),
        'available': items.filter(status='available').count(),
        'sold': items.filter(status='sold').count(),
        'returned': items.filter(status='returned').count(),
        'total_value': consignment.total_value,
        'amount_due': consignment.amount_due,
    }

    context = {
        'consignment': consignment,
        'items': items,
        'stats': stats,
    }
    return render(request, 'purchases/consignment_detail.html', context)
