"""
Sales management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, F
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from .models import SaleInvoice, SaleInvoiceItem, ClientLoan, Layaway
from products.models import Product
from clients.models import Client
from quotes.models import Quote
from users.models import ActivityLog
from settings_app.models import PaymentMethod, BankAccount


@login_required(login_url='login')
def invoice_list(request):
    """List all sales invoices with filtering and search"""
    today = timezone.now().date()

    # FIXED: Optimized query with select_related and prefetch_related
    # PHASE 3: Filter out soft-deleted invoices
    invoices = SaleInvoice.objects.filter(is_deleted=False).select_related(
        'client', 'seller', 'delivery_method', 'payment_method'
    ).prefetch_related('items__product')

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        invoices = invoices.filter(
            Q(reference__icontains=search_query) |
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query)
        )

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        invoices = invoices.filter(date__gte=date_from)
    if date_to:
        invoices = invoices.filter(date__lte=date_to)

    # Sort
    sort_by = request.GET.get('sort', '-date')
    try:
        invoices = invoices.order_by(sort_by)
    except:
        invoices = invoices.order_by('-date')

    # Pagination
    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # FIXED: Use single optimized query for statistics instead of 4 separate queries
    today_stats = SaleInvoice.objects.filter(date=today).aggregate(
        today_total=Sum('total_amount'),
        today_count=Count('id')
    )

    month_stats = SaleInvoice.objects.filter(
        date__year=today.year,
        date__month=today.month
    ).aggregate(
        month_total=Sum('total_amount'),
        month_count=Count('id')
    )

    total_stats = SaleInvoice.objects.aggregate(
        total_invoices=Count('id'),
        total_revenue=Sum('total_amount')
    )

    stats = {
        'today': today_stats['today_total'] or Decimal('0'),
        'today_count': today_stats['today_count'] or 0,
        'month': month_stats['month_total'] or Decimal('0'),
        'month_count': month_stats['month_count'] or 0,
        'total_invoices': total_stats['total_invoices'] or 0,
        'total_revenue': total_stats['total_revenue'] or Decimal('0'),
    }

    context = {
        'page_obj': page_obj,
        'invoices': page_obj.object_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'stats': stats,
        'statuses': SaleInvoice.Status.choices,
    }

    return render(request, 'sales/invoice_list.html', context)


@login_required(login_url='login')
def invoice_detail(request, reference):
    """Display invoice details"""
    invoice = get_object_or_404(
        SaleInvoice.objects.select_related(
            'client', 'seller', 'delivery_method'
        ).prefetch_related('items'),
        reference=reference
    )

    # Log view activity
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.VIEW,
        model_name='SaleInvoice',
        object_id=str(invoice.id),
        object_repr=invoice.reference,
        ip_address=get_client_ip(request)
    )

    # Get all products (except sold) for the add item modal
    # Include available, reserved, in_repair, consigned items, etc.
    # Exclude only: SOLD, CUSTOM_ORDER
    products = Product.objects.exclude(
        status__in=['sold', 'custom_order']
    ).order_by('name')

    context = {
        'invoice': invoice,
        'items': invoice.items.all(),
        'products': products,
    }

    return render(request, 'sales/invoice_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def add_invoice_item(request, reference):
    """Add an item to an existing invoice"""
    try:
        # Get the invoice
        invoice = get_object_or_404(SaleInvoice, reference=reference)

        # Check if invoice is in draft status
        if invoice.status != 'draft':
            return JsonResponse({
                'success': False,
                'error': 'Seules les factures en brouillon peuvent avoir des articles ajoutés'
            }, status=400)

        # Get the product
        product_id = request.POST.get('product_id')
        if not product_id:
            return JsonResponse({
                'success': False,
                'error': 'Produit requis'
            }, status=400)

        product = get_object_or_404(Product, id=product_id)

        # Get quantity
        try:
            quantity = Decimal(request.POST.get('quantity', '1'))
        except (InvalidOperation, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Quantité invalide'
            }, status=400)

        if quantity <= 0:
            return JsonResponse({
                'success': False,
                'error': 'La quantité doit être supérieure à 0'
            }, status=400)

        # Get unit price
        try:
            unit_price_input = request.POST.get('unit_price', '')
            if unit_price_input:
                unit_price = Decimal(unit_price_input)
            else:
                # Use product's selling price if not provided
                unit_price = Decimal(str(product.selling_price or 0))
        except (InvalidOperation, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Prix unitaire invalide'
            }, status=400)

        if unit_price < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le prix ne peut pas être négatif'
            }, status=400)

        # Get discount
        try:
            discount_amount = Decimal(request.POST.get('discount_amount', '0'))
        except (InvalidOperation, TypeError):
            discount_amount = Decimal('0')

        if discount_amount < 0:
            discount_amount = Decimal('0')

        # Calculate total
        total_amount = (quantity * unit_price) - discount_amount

        # Create the item
        item = SaleInvoiceItem.objects.create(
            invoice=invoice,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            original_price=unit_price,  # Same as unit price for simplicity
            discount_amount=discount_amount,
            total_amount=total_amount
        )

        # Log the activity
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.CREATE,
            model_name='SaleInvoiceItem',
            object_id=str(item.id),
            object_repr=f"{invoice.reference} - {product.name}",
            ip_address=get_client_ip(request)
        )

        return JsonResponse({
            'success': True,
            'message': 'Article ajouté avec succès',
            'item_id': item.id,
            'product_name': product.name
        })

    except Exception as e:
        print(f'Error adding item: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}'
        }, status=500)


@login_required(login_url='login')
@require_http_methods(["POST"])
def delete_invoice_item(request):
    """Delete an item from an invoice"""
    try:
        item_id = request.GET.get('item_id')
        if not item_id:
            return JsonResponse({
                'success': False,
                'error': 'ID d\'article requis'
            }, status=400)

        item = get_object_or_404(SaleInvoiceItem, id=item_id)
        invoice = item.invoice

        # Check if invoice is in draft status
        if invoice.status != 'draft':
            return JsonResponse({
                'success': False,
                'error': 'Seules les factures en brouillon peuvent avoir des articles supprimés'
            }, status=400)

        # Store info for logging
        product_name = item.product.name
        invoice_reference = invoice.reference

        # Delete the item
        item.delete()

        # Log the activity
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.DELETE,
            model_name='SaleInvoiceItem',
            object_id=item_id,
            object_repr=f"{invoice_reference} - {product_name}",
            ip_address=get_client_ip(request)
        )

        return JsonResponse({
            'success': True,
            'message': 'Article supprimé avec succès'
        })

    except Exception as e:
        print(f'Error deleting item: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}'
        }, status=500)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_create(request):
    """Create a new sales invoice"""
    from .forms import SaleInvoiceForm

    # Allow staff/admin users to create invoices
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de créer des factures.')
        return redirect('sales:invoice_list')

    form = None  # Initialize form variable

    if request.method == 'POST':
        try:
            # FIXED: Use form for validation
            form = SaleInvoiceForm(request.POST)

            if form.is_valid():
                # Create invoice from form
                invoice = form.save(commit=False)
                invoice.reference = generate_invoice_reference()
                invoice.date = timezone.now().date()
                invoice.seller = request.user
                invoice.created_by = request.user
                invoice.status = SaleInvoice.Status.UNPAID
                invoice.save()

                # Process articles submitted with the form
                items_data = []
                for key in request.POST:
                    if key.startswith('items[') and key.endswith(']'):
                        try:
                            import json
                            item_json = request.POST.get(key)
                            item_data = json.loads(item_json)
                            items_data.append(item_data)
                        except (json.JSONDecodeError, ValueError):
                            pass

                # Create SaleInvoiceItem records for each article
                for item_data in items_data:
                    try:
                        product = Product.objects.get(id=item_data['product_id'])
                        SaleInvoiceItem.objects.create(
                            invoice=invoice,
                            product=product,
                            quantity=Decimal(str(item_data['quantity'])),
                            unit_price=Decimal(str(item_data['unit_price'])),
                            original_price=Decimal(str(item_data['unit_price'])),
                            discount_amount=Decimal(str(item_data['discount_amount'])),
                            total_amount=Decimal(str(item_data['total_amount']))
                        )
                    except (Product.DoesNotExist, ValueError, KeyError) as e:
                        print(f'Error creating item: {str(e)}')
                        continue

                # Calculate totals (with articles if any)
                invoice.calculate_totals()

                # Handle payment amount if provided during invoice creation
                try:
                    amount_paid = Decimal(str(request.POST.get('amount_paid', '0')))
                except (InvalidOperation, ValueError):
                    amount_paid = Decimal('0')

                if amount_paid and amount_paid > 0:
                    # SET the amount_paid (not add to it)
                    invoice.amount_paid = amount_paid
                    invoice.balance_due = invoice.total_amount - amount_paid
                    invoice.update_status()
                    invoice.save(update_fields=['amount_paid', 'balance_due', 'status'])

                    # Log the payment activity
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'{invoice.reference} - Payment: {amount_paid} DH',
                        ip_address=get_client_ip(request)
                    )

                # PHASE 3: Invalidate client balance cache on new invoice
                from django.core.cache import cache
                if invoice.client:  # Only invalidate if client exists
                    cache.delete(f'client_balance_{invoice.client.id}')

                # Log activity
                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.CREATE,
                    model_name='SaleInvoice',
                    object_id=str(invoice.id),
                    object_repr=invoice.reference,
                    ip_address=get_client_ip(request)
                )

                # Message based on whether articles were added and payment recorded
                message = f'Facture "{invoice.reference}" créée'
                if items_data:
                    message += f' avec {len(items_data)} article(s)'
                if amount_paid and amount_paid > 0:
                    message += f' • Paiement: {amount_paid} DH'
                    if amount_paid >= invoice.total_amount:
                        message += ' ✓ PAYÉE EN INTÉGRALITÉ'
                    else:
                        remaining = invoice.total_amount - amount_paid
                        message += f' (Solde: {remaining} DH)'
                message += '.'
                messages.success(request, message)
                return redirect('sales:invoice_detail', reference=invoice.reference)
            else:
                # Form validation failed
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')

        except Exception as e:
            messages.error(request, f'Erreur lors de la création: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error creating invoice: {str(e)}')

    # FIXED: Create new form if GET request or POST failed
    if form is None:
        form = SaleInvoiceForm()

    context = {
        'form': form,
        'clients': Client.objects.filter(is_active=True),
        'products': Product.objects.filter(status='available').select_related(
            'category', 'metal_type', 'metal_purity', 'supplier'
        ),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
        'sale_types': SaleInvoice.SaleType.choices,
    }

    return render(request, 'sales/invoice_form.html', context)


@login_required(login_url='login')
def invoice_detail_view(request, reference):
    """Display detailed invoice with payment options"""
    invoice = get_object_or_404(
        SaleInvoice.objects.select_related(
            'client', 'seller', 'delivery_method'
        ).prefetch_related('items'),
        reference=reference
    )

    if request.method == 'POST' and request.user.can_view_reports:
        # Handle payment or status update
        action = request.POST.get('action')

        if action == 'confirm':
            invoice.status = 'confirmed'
            invoice.save()
            messages.success(request, 'Facture confirmée.')

        elif action == 'mark_delivered':
            invoice.status = 'delivered'
            invoice.delivery_status = 'delivered'
            invoice.delivery_date = timezone.now().date()
            invoice.save()
            messages.success(request, 'Facture marquée comme livrée.')

    context = {
        'invoice': invoice,
        'items': invoice.items.all(),
    }

    return render(request, 'sales/invoice_detail.html', context)


@login_required(login_url='login')
def quote_to_invoice(request, quote_id):
    """Convert a quote to an invoice"""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de créer des factures.')
        return redirect('sales:invoice_list')

    quote = get_object_or_404(Quote, id=quote_id)

    if quote.converted_sale:
        messages.warning(request, 'Ce devis a déjà été converti en facture.')
        return redirect('sales:invoice_detail', reference=quote.converted_sale.reference)

    try:
        # Create invoice from quote
        invoice = SaleInvoice.objects.create(
            reference=generate_invoice_reference(),
            date=timezone.now().date(),
            sale_type='regular',
            client=quote.client,
            seller=request.user,
            subtotal=quote.subtotal_dh,
            discount_percent=quote.discount_percent,
            discount_amount=quote.discount_amount_dh,
            tax_amount_dh=quote.tax_amount_dh,
            total_amount=quote.total_amount_dh,
            status='confirmed',
            created_by=request.user,
        )

        # Add items from quote
        for quote_item in quote.items.all():
            SaleInvoiceItem.objects.create(
                invoice=invoice,
                product=quote_item.product,
                unit_price=quote_item.unit_price_dh,
                original_price=quote_item.unit_price_dh,
            )

        # Link quote to invoice
        quote.converted_sale = invoice
        quote.status = 'converted'
        quote.save()

        # Log activity
        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.CREATE,
            model_name='SaleInvoice',
            object_id=str(invoice.id),
            object_repr=f'{invoice.reference} (from quote)',
            ip_address=get_client_ip(request)
        )

        messages.success(request, f'Devis converti en facture "{invoice.reference}".')
        return redirect('sales:invoice_detail', reference=invoice.reference)

    except Exception as e:
        messages.error(request, f'Erreur lors de la conversion: {str(e)}')
        return redirect('quotes:list')


@login_required(login_url='login')
def payment_tracking(request):
    """View payment tracking dashboard"""
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas accès à ce rapport.')
        return redirect('dashboard')

    # Get pending payments
    pending_invoices = SaleInvoice.objects.filter(
        balance_due__gt=0
    ).select_related('client', 'seller').order_by('-date')

    # Statistics
    total_pending = pending_invoices.aggregate(
        total=Sum('balance_due')
    )['total'] or 0

    overdue_invoices = pending_invoices.filter(
        date__lt=timezone.now().date() - timezone.timedelta(days=30)
    ).count()

    context = {
        'pending_invoices': pending_invoices[:50],
        'total_pending': total_pending,
        'overdue_count': overdue_invoices,
    }

    return render(request, 'sales/payment_tracking.html', context)


def generate_invoice_reference():
    """Generate unique invoice reference"""
    from django.utils import timezone
    today = timezone.now().date()
    count = SaleInvoice.objects.filter(date=today).count() + 1
    return f'INV-{today.strftime("%Y%m%d")}-{count:04d}'


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ============================================================================
# PHASE 2: MISSING ENDPOINTS (Invoice Edit, Delete, Payment, Delivery)
# ============================================================================

@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_edit(request, reference):
    """Edit existing invoice (DRAFT invoices only)"""
    from .forms import SaleInvoiceForm

    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Check status - only draft can be edited
    if invoice.status != SaleInvoice.Status.DRAFT:
        messages.error(request, 'Seuls les brouillons peuvent être édités.')
        return redirect('sales:invoice_detail', reference=reference)

    # Check permissions
    if request.user != invoice.created_by and not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'éditer cette facture.')
        return redirect('sales:invoice_detail', reference=reference)

    form = None

    if request.method == 'POST':
        try:
            form = SaleInvoiceForm(request.POST, instance=invoice)
            if form.is_valid():
                form.save()
                invoice.calculate_totals()

                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='SaleInvoice',
                    object_id=str(invoice.id),
                    object_repr=invoice.reference,
                    ip_address=get_client_ip(request)
                )

                messages.success(request, 'Facture mise à jour avec succès.')
                return redirect('sales:invoice_detail', reference=reference)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
        except Exception as e:
            messages.error(request, f'Erreur lors de la mise à jour: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error editing invoice {reference}: {str(e)}')

    if form is None:
        form = SaleInvoiceForm(instance=invoice)

    context = {
        'invoice': invoice,
        'form': form,
        'clients': Client.objects.filter(is_active=True),
    }

    return render(request, 'sales/invoice_edit.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_delete(request, reference):
    """Delete (soft delete) invoice - only DRAFT invoices"""
    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Only allow deleting DRAFT invoices
    if invoice.status != SaleInvoice.Status.DRAFT:
        messages.error(request, 'Seules les factures brouillons peuvent être supprimées.')
        return redirect('sales:invoice_detail', reference=reference)

    # Check permissions
    if request.user != invoice.created_by and not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de supprimer cette facture.')
        return redirect('sales:invoice_detail', reference=reference)

    if request.method == 'POST':
        try:
            # Use model soft_delete method
            invoice.soft_delete()

            # PHASE 3: Invalidate client balance cache (only if client exists)
            from django.core.cache import cache
            if invoice.client:  # Only invalidate if client exists
                cache.delete(f'client_balance_{invoice.client.id}')

            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.DELETE,
                model_name='SaleInvoice',
                object_id=str(invoice.id),
                object_repr=invoice.reference,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Facture {invoice.reference} supprimée.')
            return redirect('sales:invoice_list')
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error deleting invoice {reference}: {str(e)}')

    context = {'invoice': invoice}
    return render(request, 'sales/invoice_delete.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_payment(request, reference):
    """Record payment for invoice"""
    from .forms import PaymentForm

    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Check permissions
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'enregistrer un paiement.')
        return redirect('sales:invoice_detail', reference=reference)

    form = None

    if request.method == 'POST':
        try:
            form = PaymentForm(request.POST)
            if form.is_valid():
                amount = form.cleaned_data['amount']

                # Validate amount doesn't exceed balance
                if amount > invoice.balance_due:
                    messages.error(
                        request,
                        f'Le paiement ne peut pas dépasser le solde dû ({invoice.balance_due} DH)'
                    )
                else:
                    # Record payment in activity log (or payment model if exists)
                    # Update invoice payment status
                    paid_amount = invoice.amount_paid + amount

                    if paid_amount >= invoice.total_amount:
                        invoice.status = SaleInvoice.Status.PAID
                    elif paid_amount > 0:
                        invoice.status = SaleInvoice.Status.PARTIAL

                    invoice.amount_paid = paid_amount
                    invoice.save(update_fields=['status', 'amount_paid'])

                    # Log activity
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.CREATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'{invoice.reference} - Paiement {amount} DH',
                        ip_address=get_client_ip(request)
                    )

                    messages.success(request, f'Paiement de {amount} DH enregistré.')
                    return redirect('sales:invoice_detail', reference=reference)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
        except Exception as e:
            messages.error(request, f'Erreur lors de l\'enregistrement du paiement: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error recording payment for {reference}: {str(e)}')

    if form is None:
        form = PaymentForm()

    context = {
        'invoice': invoice,
        'form': form,
        'remaining': invoice.balance_due,
    }

    return render(request, 'sales/invoice_payment.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_delivery(request, reference):
    """Update delivery information"""
    from .forms import DeliveryForm

    invoice = get_object_or_404(SaleInvoice, reference=reference)

    # Check permissions
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de mettre à jour la livraison.')
        return redirect('sales:invoice_detail', reference=reference)

    form = None

    if request.method == 'POST':
        try:
            form = DeliveryForm(request.POST, instance=invoice)
            if form.is_valid():
                form.save()

                # Update status if delivered
                if form.cleaned_data.get('delivery_status') == 'delivered':
                    invoice.delivery_date = timezone.now().date()
                    invoice.status = SaleInvoice.Status.DELIVERED
                    invoice.save(update_fields=['delivery_date', 'status'])

                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='SaleInvoice',
                    object_id=str(invoice.id),
                    object_repr=f'{invoice.reference} - Livraison',
                    ip_address=get_client_ip(request)
                )

                messages.success(request, 'Informations de livraison mises à jour.')
                return redirect('sales:invoice_detail', reference=reference)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
        except Exception as e:
            messages.error(request, f'Erreur lors de la mise à jour de la livraison: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error updating delivery for {reference}: {str(e)}')

    if form is None:
        form = DeliveryForm(instance=invoice)

    context = {
        'invoice': invoice,
        'form': form,
    }

    return render(request, 'sales/invoice_delivery.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def get_payment_methods(request):
    """API endpoint to get payment methods with requires_reference info"""
    payment_methods = PaymentMethod.objects.filter(is_active=True).values('id', 'name', 'requires_reference')
    return JsonResponse({
        'payment_methods': list(payment_methods)
    })
