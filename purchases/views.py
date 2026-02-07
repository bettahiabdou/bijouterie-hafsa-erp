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
@permission_required('purchases.add_purchaseinvoice', raise_exception=True)
def purchase_invoice_create(request):
    """Create new purchase invoice"""
    if request.method == 'POST':
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

    from suppliers.models import Supplier
    context = {
        'suppliers': Supplier.objects.all(),
        'purchase_orders': PurchaseOrder.objects.filter(status='approved'),
        'type_choices': PurchaseInvoice.InvoiceType.choices,
    }
    return render(request, 'purchases/purchase_invoice_form.html', context)


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

        # Handle add product action
        elif action == 'add_product':
            product_id = request.POST.get('product_id')
            if product_id:
                try:
                    product = Product.objects.get(id=product_id)
                    # Create a new invoice item linked to this product
                    PurchaseInvoiceItem.objects.create(
                        invoice=invoice,
                        product=product,
                        description=f"{product.name} - {product.reference}",
                        category=product.category,
                        metal_type=product.metal_type,
                        metal_purity=product.metal_purity,
                        gross_weight=product.gross_weight or 0,
                        net_weight=product.net_weight or 0,
                        price_per_gram=product.purchase_price_per_gram or 0,
                        labor_cost=product.labor_cost or 0,
                        quantity=1
                    )
                    # Update invoice totals
                    invoice.calculate_totals()
                    invoice.save()

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='PurchaseInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'Added product {product.reference} to invoice {invoice.reference}',
                        ip_address=get_client_ip(request)
                    )
                    messages.success(request, f'Produit {product.reference} ajouté à la facture.')
                except Product.DoesNotExist:
                    messages.error(request, 'Produit non trouvé.')

        # Handle remove item action
        elif action == 'remove_item':
            item_id = request.POST.get('item_id')
            if item_id:
                try:
                    item = PurchaseInvoiceItem.objects.get(id=item_id, invoice=invoice)
                    item_desc = item.description
                    item.delete()
                    # Update invoice totals
                    invoice.calculate_totals()
                    invoice.save()

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.DELETE,
                        model_name='PurchaseInvoiceItem',
                        object_id=str(item_id),
                        object_repr=f'Removed item {item_desc} from invoice {invoice.reference}',
                        ip_address=get_client_ip(request)
                    )
                    messages.success(request, f'Article supprimé de la facture.')
                except PurchaseInvoiceItem.DoesNotExist:
                    messages.error(request, 'Article non trouvé.')

        return redirect('purchases:purchase_invoice_detail', reference=reference)

    # Get all products for the add product modal (regardless of status)
    all_products = Product.objects.select_related(
        'category', 'metal_type', 'metal_purity'
    ).order_by('-created_at')[:100]  # Limit to recent 100

    context = {
        'invoice': invoice,
        'items': invoice.items.select_related('product').all(),
        'all_products': all_products,
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
