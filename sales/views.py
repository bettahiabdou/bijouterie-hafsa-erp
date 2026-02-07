"""
Sales management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count, Sum, F
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from .models import SaleInvoice, SaleInvoiceItem, SaleInvoiceAction, ClientLoan, Layaway
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

    # Sort - Use whitelist for safety
    ALLOWED_SORTS = {
        'date': '-date',
        '-date': '-date',
        'amount': 'total_amount',
        '-amount': '-total_amount',
        'client': 'client__first_name',
        '-client': '-client__first_name',
        'status': 'status',
        '-status': '-status',
        'paid': 'amount_paid',
        '-paid': '-amount_paid',
    }
    sort_param = request.GET.get('sort', '-date')
    sort_by = ALLOWED_SORTS.get(sort_param, '-date')
    invoices = invoices.order_by(sort_by)

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
        ).prefetch_related('items', 'items__product'),
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

    # Handle POST actions for return/exchange
    if request.method == 'POST':
        action = request.POST.get('action')

        # Handle return action
        if action == 'return_item':
            item_id = request.POST.get('item_id')
            notes = request.POST.get('notes', '')

            if item_id:
                try:
                    item = SaleInvoiceItem.objects.get(id=item_id, invoice=invoice)
                    product = item.product
                    product_ref = product.reference

                    # Create action record
                    SaleInvoiceAction.objects.create(
                        original_invoice=invoice,
                        action_type=SaleInvoiceAction.ActionType.RETURN,
                        original_product=product,
                        original_product_ref=product_ref,
                        refund_amount=item.total_amount,
                        notes=notes,
                        created_by=request.user
                    )

                    # Update product status to available
                    product.status = 'available'
                    product.save(update_fields=['status'])

                    # Update original invoice status to returned
                    invoice.status = SaleInvoice.Status.RETURNED
                    invoice.save(update_fields=['status'])

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'Returned product {product_ref} from invoice {invoice.reference}',
                        ip_address=get_client_ip(request)
                    )
                    messages.success(request, f'Produit {product_ref} retourné. Facture marquée comme retournée.')

                except SaleInvoiceItem.DoesNotExist:
                    messages.error(request, 'Article non trouvé.')

        # Handle exchange action (supports multiple products and payment)
        elif action == 'exchange_item':
            import json

            item_id = request.POST.get('item_id')
            replacement_products_json = request.POST.get('replacement_products', '[]')
            new_invoice_reference = request.POST.get('new_invoice_reference', '').strip()
            payment_method_id = request.POST.get('payment_method_id', '')
            payment_reference = request.POST.get('payment_reference', '').strip()
            bank_account_id = request.POST.get('bank_account_id', '')
            amount_paid_str = request.POST.get('amount_paid', '0')
            notes = request.POST.get('notes', '')

            try:
                replacement_products_data = json.loads(replacement_products_json)
            except json.JSONDecodeError:
                replacement_products_data = []

            if item_id and replacement_products_data:
                try:
                    item = SaleInvoiceItem.objects.get(id=item_id, invoice=invoice)
                    original_product = item.product
                    original_ref = original_product.reference

                    # Validate all replacement products are available
                    replacement_refs = []
                    for prod_data in replacement_products_data:
                        prod = Product.objects.get(id=prod_data['id'])
                        if prod.status == 'sold':
                            messages.error(request, f'{prod.reference} est déjà vendu.')
                            return redirect('sales:invoice_detail', reference=reference)
                        replacement_refs.append(prod.reference)

                    # Handle custom reference for new invoice
                    if new_invoice_reference:
                        # Check if reference already exists
                        if SaleInvoice.objects.filter(reference=new_invoice_reference).exists():
                            messages.error(request, f'La référence "{new_invoice_reference}" existe déjà. Veuillez en choisir une autre.')
                            return redirect('sales:invoice_detail', reference=reference)
                        exchange_reference = new_invoice_reference
                    else:
                        exchange_reference = generate_invoice_reference()

                    # Create new invoice for the exchange
                    new_invoice = SaleInvoice.objects.create(
                        reference=exchange_reference,
                        date=timezone.now().date(),
                        sale_type=invoice.sale_type,
                        client=invoice.client,
                        seller=request.user,
                        created_by=request.user,
                        notes=f"Échange depuis {invoice.reference} - {original_ref} → {', '.join(replacement_refs)}",
                    )

                    # Add payment method if provided
                    if payment_method_id:
                        try:
                            payment_method = PaymentMethod.objects.get(id=payment_method_id)
                            new_invoice.payment_method = payment_method
                            if payment_reference:
                                new_invoice.payment_reference = payment_reference
                            if bank_account_id:
                                try:
                                    bank_account = BankAccount.objects.get(id=bank_account_id)
                                    new_invoice.bank_account = bank_account
                                except BankAccount.DoesNotExist:
                                    pass
                        except PaymentMethod.DoesNotExist:
                            pass

                    # Add all replacement products to new invoice with custom prices
                    first_replacement = None
                    for prod_data in replacement_products_data:
                        replacement_product = Product.objects.get(id=prod_data['id'])
                        custom_price = Decimal(str(prod_data.get('price', replacement_product.selling_price)))

                        if first_replacement is None:
                            first_replacement = replacement_product

                        SaleInvoiceItem.objects.create(
                            invoice=new_invoice,
                            product=replacement_product,
                            quantity=1,
                            original_price=replacement_product.selling_price,
                            negotiated_price=custom_price,
                            unit_price=custom_price,
                            total_amount=custom_price,
                        )

                        # Update replacement product status to sold
                        replacement_product.status = 'sold'
                        replacement_product.save(update_fields=['status'])

                    # Calculate totals for new invoice
                    new_invoice.calculate_totals()

                    # Handle payment amount
                    # The logic: original price is already "paid" from the exchanged invoice
                    # So the client only needs to pay the DIFFERENCE (if positive)
                    try:
                        amount_paid_input = Decimal(amount_paid_str)
                    except (InvalidOperation, ValueError):
                        amount_paid_input = Decimal('0')

                    # Calculate the difference to pay
                    original_item_price = item.total_amount  # Price from original invoice
                    difference = new_invoice.total_amount - original_item_price

                    if difference <= 0:
                        # New products cost less or equal - invoice is fully paid
                        # The "credit" from original covers everything
                        new_invoice.amount_paid = new_invoice.total_amount
                        new_invoice.balance_due = Decimal('0')
                        new_invoice.status = SaleInvoice.Status.PAID
                    else:
                        # Client needs to pay the difference
                        # amount_paid_input is what they pay NOW for the difference
                        # Total amount_paid = original_item_price + what they pay now
                        total_effectively_paid = original_item_price + amount_paid_input

                        if total_effectively_paid >= new_invoice.total_amount:
                            new_invoice.amount_paid = new_invoice.total_amount
                            new_invoice.balance_due = Decimal('0')
                            new_invoice.status = SaleInvoice.Status.PAID
                        elif amount_paid_input > 0:
                            new_invoice.amount_paid = total_effectively_paid
                            new_invoice.balance_due = new_invoice.total_amount - total_effectively_paid
                            new_invoice.status = SaleInvoice.Status.PARTIAL_PAID
                        else:
                            # No additional payment - only original price credited
                            new_invoice.amount_paid = original_item_price
                            new_invoice.balance_due = difference
                            new_invoice.status = SaleInvoice.Status.PARTIAL_PAID

                    new_invoice.save()

                    # Create action record (link to first replacement product for reference)
                    SaleInvoiceAction.objects.create(
                        original_invoice=invoice,
                        action_type=SaleInvoiceAction.ActionType.EXCHANGE,
                        original_product=original_product,
                        original_product_ref=original_ref,
                        new_invoice=new_invoice,
                        replacement_product=first_replacement,
                        notes=notes,
                        created_by=request.user
                    )

                    # Update original product status to available
                    original_product.status = 'available'
                    original_product.save(update_fields=['status'])

                    # Update original invoice status to exchanged
                    invoice.status = SaleInvoice.Status.EXCHANGED
                    invoice.save(update_fields=['status'])

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'Exchanged {original_ref} for {", ".join(replacement_refs)}',
                        ip_address=get_client_ip(request)
                    )

                    # Create success message
                    status_msg = ''
                    if new_invoice.status == SaleInvoice.Status.PAID:
                        status_msg = ' ✓ Payée'
                    elif new_invoice.status == SaleInvoice.Status.PARTIAL_PAID:
                        status_msg = f' - Solde: {new_invoice.balance_due} DH'
                    else:
                        status_msg = f' - À payer: {new_invoice.balance_due} DH'

                    messages.success(
                        request,
                        f'Échange effectué: {original_ref} → {", ".join(replacement_refs)}. '
                        f'Nouvelle facture: {new_invoice.reference}{status_msg}'
                    )

                except SaleInvoiceItem.DoesNotExist:
                    messages.error(request, 'Article non trouvé.')
                except Product.DoesNotExist:
                    messages.error(request, 'Produit de remplacement non trouvé.')

        return redirect('sales:invoice_detail', reference=reference)

    # Get all products (except sold) for the add item modal
    # Include available, reserved, in_repair, consigned items, etc.
    # Exclude only: SOLD, CUSTOM_ORDER
    products = Product.objects.exclude(
        status__in=['sold', 'custom_order']
    ).order_by('name')

    # Get available products for exchange (available only)
    exchange_products = Product.objects.filter(
        status='available'
    ).select_related('category', 'metal_type', 'metal_purity').order_by('-created_at')[:100]

    # Get action history
    invoice_actions = invoice.actions.select_related(
        'original_product', 'replacement_product', 'new_invoice', 'created_by'
    ).all()

    # Get payment methods and bank accounts for exchange modal
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)

    context = {
        'invoice': invoice,
        'items': invoice.items.all(),
        'products': products,
        'exchange_products': exchange_products,
        'invoice_actions': invoice_actions,
        'payment_methods': payment_methods,
        'bank_accounts': bank_accounts,
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

    except SaleInvoice.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Facture non trouvée'
        }, status=404)
    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Produit non trouvé'
        }, status=404)
    except (IntegrityError, ValueError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f'Validation error adding item: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': 'Données invalides'
        }, status=400)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Unexpected error adding invoice item: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': 'Erreur serveur'
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

    except SaleInvoiceItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Article non trouvé'
        }, status=404)
    except PermissionDenied:
        return JsonResponse({
            'success': False,
            'error': 'Vous n\'avez pas la permission de supprimer cet article'
        }, status=403)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Unexpected error deleting invoice item: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': 'Erreur serveur'
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

                # Handle custom reference - use provided one or auto-generate
                custom_reference = request.POST.get('custom_reference', '').strip()
                if custom_reference:
                    # Check if reference already exists
                    if SaleInvoice.objects.filter(reference=custom_reference).exists():
                        messages.error(request, f'La référence "{custom_reference}" existe déjà. Veuillez en choisir une autre.')
                        form = SaleInvoiceForm(request.POST)
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
                    invoice.reference = custom_reference
                else:
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

                        # Get the entered price and calculate discount properly
                        entered_price = Decimal(str(item_data['unit_price']))
                        catalog_price = product.selling_price or entered_price
                        manual_discount = Decimal(str(item_data.get('discount_amount', 0)))

                        # If price was changed from catalog price, that's also a discount
                        price_difference = catalog_price - entered_price
                        total_discount = manual_discount + max(Decimal('0'), price_difference)

                        SaleInvoiceItem.objects.create(
                            invoice=invoice,
                            product=product,
                            quantity=Decimal(str(item_data['quantity'])),
                            unit_price=entered_price,
                            original_price=catalog_price,  # Product's catalog price
                            negotiated_price=entered_price,  # The actual sale price
                            discount_amount=total_discount,
                            total_amount=Decimal(str(item_data['total_amount']))
                        )

                        # RESERVE PRODUCT: Mark as 'indisponible' when invoice is created
                        # Product will be either 'sold' (if paid) or stay 'indisponible' (if unpaid/partial)
                        product.status = 'indisponible'
                        product.save(update_fields=['status'])
                    except (Product.DoesNotExist, ValueError, KeyError) as e:
                        print(f'Error creating item: {str(e)}')
                        continue

                # Calculate totals (with articles if any)
                invoice.calculate_totals()

                # VALIDATION: Require at least 1 item in invoice
                if invoice.items.count() == 0:
                    messages.error(request, 'Une facture doit contenir au moins un article.')
                    invoice.delete()  # Clean up empty invoice
                    return redirect('sales:invoice_create')

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

                    # UPDATE PRODUCT STATUS: If invoice is now PAID, mark product as sold
                    if invoice.status == SaleInvoice.Status.PAID:
                        for item in invoice.items.all():
                            item.product.status = 'sold'
                            item.product.save(update_fields=['status'])
                    # Note: if status is UNPAID or PARTIAL, product stays 'indisponible' (reserved)

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

        except IntegrityError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Integrity error creating invoice: {str(e)}')
            messages.error(request, 'Erreur: données dupliquées ou invalides')
        except ValueError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Validation error creating invoice: {str(e)}')
            messages.error(request, f'Erreur: {str(e)}')
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Unexpected error creating invoice: {str(e)}')
            messages.error(request, 'Erreur serveur lors de la création')

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
def bulk_invoice_create(request):
    """Create multiple invoices at once (bulk sales)

    Since sales invoices don't have common fields (each client/product is different),
    we create a table-based form where each row is a complete invoice with:
    - Client selection (optional for walk-in sales)
    - Product selection
    - Quantity
    - Selling price (can override product default)
    - Payment method & reference (optional, for partial/full payment at creation)
    """
    if request.method == 'POST':
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Extract invoice rows from form
            custom_references = request.POST.getlist('custom_reference')
            client_ids = request.POST.getlist('client_id')
            product_ids = request.POST.getlist('product_id')
            quantities = request.POST.getlist('quantity')
            selling_prices = request.POST.getlist('selling_price')
            payment_methods = request.POST.getlist('payment_method')
            payment_references = request.POST.getlist('payment_reference')
            amount_paids = request.POST.getlist('amount_paid')
            bank_accounts = request.POST.getlist('bank_account')
            discount_amounts = request.POST.getlist('discount_amount')

            # ============================================
            # SERVER-SIDE VALIDATION
            # ============================================

            # Track products and references used in this batch
            used_product_ids = []
            used_payment_refs = []
            used_custom_refs = []
            validation_errors = []

            for i, product_id_str in enumerate(product_ids):
                if not product_id_str:
                    continue

                # Check for duplicate products in the same batch
                if product_id_str in used_product_ids:
                    validation_errors.append(f"Ligne {i + 1}: Produit déjà utilisé dans une autre ligne")
                else:
                    used_product_ids.append(product_id_str)

                # Check for duplicate custom references in the same batch
                custom_ref = custom_references[i].strip() if i < len(custom_references) else ''
                if custom_ref:
                    if custom_ref in used_custom_refs:
                        validation_errors.append(f"Ligne {i + 1}: Référence de facture '{custom_ref}' déjà utilisée dans une autre ligne")
                    else:
                        used_custom_refs.append(custom_ref)

                    # Check if custom reference already exists in database
                    if SaleInvoice.objects.filter(reference=custom_ref).exists():
                        validation_errors.append(f"Ligne {i + 1}: Référence de facture '{custom_ref}' existe déjà dans la base de données")

                # Check for duplicate payment references in the same batch
                payment_ref = payment_references[i].strip() if i < len(payment_references) else ''
                if payment_ref:
                    if payment_ref in used_payment_refs:
                        validation_errors.append(f"Ligne {i + 1}: Référence de paiement '{payment_ref}' déjà utilisée dans une autre ligne")
                    else:
                        used_payment_refs.append(payment_ref)

                    # Check if payment reference already exists in database
                    if SaleInvoice.objects.filter(payment_reference__iexact=payment_ref).exists():
                        validation_errors.append(f"Ligne {i + 1}: Référence de paiement '{payment_ref}' existe déjà dans la base de données")

            # If there are validation errors, stop and show them
            if validation_errors:
                for error in validation_errors:
                    messages.error(request, error)
                return redirect('sales:bulk_create')

            # ============================================
            # END VALIDATION - START PROCESSING
            # ============================================

            created_count = 0
            failed_rows = []

            for i, product_id_str in enumerate(product_ids):
                try:
                    # Skip empty rows
                    if not product_id_str:
                        continue

                    product_id = int(product_id_str)
                    product = Product.objects.get(id=product_id)

                    # Get quantity
                    quantity_str = quantities[i] if i < len(quantities) else '1'
                    quantity = Decimal(quantity_str) if quantity_str else Decimal(1)

                    if quantity <= 0:
                        failed_rows.append((i + 1, 'Quantité doit être positive'))
                        continue

                    # Get custom reference or generate one
                    custom_ref = custom_references[i].strip() if i < len(custom_references) else ''
                    reference = custom_ref if custom_ref else generate_invoice_reference()

                    # Get client (optional for walk-in sales)
                    client_id = client_ids[i] if i < len(client_ids) and client_ids[i] else None
                    client = Client.objects.get(id=client_id) if client_id else None

                    # Get selling price (use product default or override)
                    selling_price = product.selling_price
                    if i < len(selling_prices) and selling_prices[i].strip():
                        try:
                            selling_price = Decimal(selling_prices[i])
                        except (ValueError, InvalidOperation):
                            pass

                    # Get discount amount if provided (auto-calculated as difference from original price)
                    discount_amount = Decimal(0)
                    if i < len(discount_amounts) and discount_amounts[i].strip():
                        try:
                            discount_amount = Decimal(discount_amounts[i])
                            if discount_amount < 0:
                                discount_amount = Decimal(0)
                        except (ValueError, InvalidOperation):
                            discount_amount = Decimal(0)

                    # Calculate prices:
                    # - subtotal = original price (before discount)
                    # - total_amount = selling price (after discount/negotiation)
                    # - discount_amount = difference between original and selling
                    original_price = product.selling_price or Decimal('0')
                    subtotal = original_price * quantity  # Original price
                    total_amount = selling_price * quantity  # Negotiated/sale price
                    calculated_discount = subtotal - total_amount  # Auto-calculated discount

                    # Use calculated discount if no manual discount provided
                    if discount_amount == 0 and calculated_discount > 0:
                        discount_amount = calculated_discount

                    # Create invoice
                    invoice = SaleInvoice.objects.create(
                        reference=reference,
                        date=timezone.now().date(),
                        client=client,
                        seller=request.user,
                        status=SaleInvoice.Status.UNPAID,
                        subtotal=subtotal,
                        discount_amount=discount_amount,
                        total_amount=total_amount,
                        amount_paid=Decimal(0),
                    )

                    # Add product item to invoice
                    # original_price = product's catalog price
                    # negotiated_price = the price entered by user (selling_price)
                    # unit_price will be set by SaleInvoiceItem.save() based on negotiated_price
                    original_price = product.selling_price or Decimal('0')

                    SaleInvoiceItem.objects.create(
                        invoice=invoice,
                        product=product,
                        quantity=quantity,
                        original_price=original_price,
                        negotiated_price=selling_price,  # The actual sale price
                        unit_price=selling_price,
                        total_amount=selling_price * quantity,
                    )

                    # RESERVE PRODUCT: Mark as 'indisponible' when invoice is created
                    # Product will be either 'sold' (if paid) or stay 'indisponible' (if unpaid/partial)
                    product.status = 'indisponible'
                    product.save(update_fields=['status'])

                    # Handle payment method & reference if provided
                    if i < len(payment_methods) and payment_methods[i]:
                        payment_method_id = payment_methods[i]
                        payment_reference = payment_references[i] if i < len(payment_references) else ''
                        bank_account_id = bank_accounts[i] if i < len(bank_accounts) and bank_accounts[i] else None

                        try:
                            payment_method = PaymentMethod.objects.get(id=payment_method_id)
                            invoice.payment_method = payment_method
                            # Set payment_reference to None if empty (to avoid UNIQUE constraint on empty strings)
                            invoice.payment_reference = payment_reference if payment_reference.strip() else None

                            # Set bank account for virement bancaire payments
                            if bank_account_id:
                                try:
                                    bank_account = BankAccount.objects.get(id=bank_account_id)
                                    invoice.bank_account = bank_account
                                except BankAccount.DoesNotExist:
                                    pass

                            invoice.save(update_fields=['payment_method', 'payment_reference', 'bank_account'])
                        except PaymentMethod.DoesNotExist:
                            pass

                    # Handle amount paid if provided (for partial/full payment at creation)
                    if i < len(amount_paids) and amount_paids[i].strip():
                        try:
                            amount_paid = Decimal(amount_paids[i])
                            if amount_paid > 0:
                                invoice.amount_paid = amount_paid

                                # Call update_status() to properly set status AND balance_due
                                # This ensures balance_due = 0 when PAID, and correct balance otherwise
                                invoice.update_status()

                                invoice.save(update_fields=['amount_paid', 'status', 'balance_due'])

                                # UPDATE PRODUCT STATUS: Change status based on final invoice status
                                # This must be done AFTER invoice status is updated (not in SaleInvoiceItem.save)
                                if invoice.status == SaleInvoice.Status.PAID:
                                    # Get the product from the invoice items
                                    for item in invoice.items.all():
                                        item.product.status = 'sold'
                                        item.product.save(update_fields=['status'])
                                # Note: if status is UNPAID or PARTIAL, product stays 'indisponible' (reserved)

                                # Log payment activity
                                ActivityLog.objects.create(
                                    user=request.user,
                                    action=ActivityLog.ActionType.CREATE,
                                    model_name='Payment',
                                    object_id=str(invoice.id),
                                    object_repr=f'Paiement {amount_paid} DH - {invoice.reference}',
                                    ip_address=get_client_ip(request)
                                )
                        except (ValueError, InvalidOperation):
                            pass

                    # Log invoice creation
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.CREATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=invoice.reference,
                        ip_address=get_client_ip(request)
                    )

                    created_count += 1

                except Product.DoesNotExist:
                    failed_rows.append((i + 1, 'Produit non trouvé'))
                    logger.warning(f'Product not found for bulk invoice at row {i + 1}')
                    continue
                except (ValueError, TypeError) as e:
                    failed_rows.append((i + 1, str(e)))
                    logger.warning(f'Failed to create bulk invoice at row {i + 1}: {str(e)}')
                    continue
                except Exception as e:
                    failed_rows.append((i + 1, str(e)))
                    logger.exception(f'Unexpected error creating bulk invoice at row {i + 1}')
                    continue

            # Provide success/warning feedback
            if created_count > 0:
                messages.success(request, f'{created_count} facture(s) créée(s) avec succès.')

            if failed_rows:
                error_details = '; '.join([f"Ligne {row}: {error}" for row, error in failed_rows])
                messages.warning(request, f'Certaines lignes n\'ont pas pu être créées: {error_details}')

            return redirect('sales:invoice_list')

        except Exception as e:
            logger.exception(f'Error in bulk invoice creation: {str(e)}')
            messages.error(request, f'Erreur lors de la création en lot: {str(e)}')

    # Get context data
    context = {
        'clients': Client.objects.filter(is_active=True),
        'products': Product.objects.filter(status='available'),
        'payment_methods': PaymentMethod.objects.filter(is_active=True),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
    }

    return render(request, 'sales/bulk_invoice_form.html', context)


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
                payment_method = form.cleaned_data.get('payment_method')
                payment_reference = form.cleaned_data.get('payment_reference', '').strip()
                bank_account = form.cleaned_data.get('bank_account')

                # SECURITY: Use transaction lock to prevent race conditions
                from django.db import transaction
                with transaction.atomic():
                    # Re-fetch with lock to get current state
                    invoice = SaleInvoice.objects.select_for_update().get(id=invoice.id)

                    # Validate amount doesn't exceed balance (re-check after lock)
                    if amount > invoice.balance_due:
                        messages.error(
                            request,
                            f'Le paiement ne peut pas dépasser le solde dû ({invoice.balance_due} DH)'
                        )
                    else:
                        # SECURITY: Check for duplicate payment (same amount within 10 seconds)
                        from django.utils import timezone
                        from datetime import timedelta

                        recent_payments = ActivityLog.objects.filter(
                            user=request.user,
                            action=ActivityLog.ActionType.CREATE,
                            model_name='SaleInvoice',
                            object_id=str(invoice.id),
                            created_at__gte=timezone.now() - timedelta(seconds=10),
                            object_repr__icontains=f'Paiement {amount} DH'
                        ).count()

                        if recent_payments > 0:
                            messages.error(
                                request,
                                'Un paiement de ce montant a été enregistré récemment. Veuillez patienter.'
                            )
                        else:
                            # Record payment in activity log (or payment model if exists)
                            # Update invoice payment status
                            paid_amount = invoice.amount_paid + amount

                            if paid_amount >= invoice.total_amount:
                                invoice.status = SaleInvoice.Status.PAID
                            elif paid_amount > 0:
                                invoice.status = SaleInvoice.Status.PARTIAL_PAID

                            invoice.amount_paid = paid_amount

                            # Update payment method details if provided
                            if payment_method:
                                invoice.payment_method = payment_method
                            if payment_reference:
                                invoice.payment_reference = payment_reference
                            if bank_account:
                                invoice.bank_account = bank_account

                            # Determine which fields to update
                            update_fields = ['status', 'amount_paid']
                            if payment_method:
                                update_fields.append('payment_method')
                            if payment_reference:
                                update_fields.append('payment_reference')
                            if bank_account:
                                update_fields.append('bank_account')

                            invoice.save(update_fields=update_fields)

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


# ============================================================================
# PENDING INVOICES (BROUILLON) - Created via Telegram
# ============================================================================

@login_required(login_url='login')
def pending_invoices_list(request):
    """List all draft invoices pending data entry"""
    # Get draft invoices with photos
    invoices = SaleInvoice.objects.filter(
        status=SaleInvoice.Status.DRAFT,
        is_deleted=False
    ).select_related('seller').prefetch_related('photos').order_by('-created_at')

    # Filter by seller (for non-admin users, show only their own)
    if not request.user.is_admin and not request.user.is_manager:
        invoices = invoices.filter(seller=request.user)

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        invoices = invoices.filter(
            Q(reference__icontains=search_query) |
            Q(seller__username__icontains=search_query) |
            Q(seller__first_name__icontains=search_query)
        )

    # Stats
    stats = {
        'total_pending': invoices.count(),
        'today_pending': invoices.filter(date=timezone.now().date()).count(),
    }

    # Pagination
    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'invoices': page_obj,
        'stats': stats,
        'search_query': search_query,
    }

    return render(request, 'sales/pending_invoices_list.html', context)


@login_required(login_url='login')
def pending_invoice_complete(request, reference):
    """Complete a draft invoice - add products and finalize"""
    from settings_app.models import ProductCategory, MetalType, MetalPurity

    invoice = get_object_or_404(
        SaleInvoice.objects.select_related('seller', 'client').prefetch_related('photos', 'items__product'),
        reference=reference,
        is_deleted=False
    )

    # Check if invoice is still draft
    if invoice.status != SaleInvoice.Status.DRAFT:
        messages.error(request, "Cette facture a déjà été validée.")
        return redirect('sales:invoice_detail', reference=reference)

    # Handle form submission
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_item':
            # Add existing product to invoice
            product_id = request.POST.get('product_id')
            quantity = request.POST.get('quantity', 1)
            selling_price = request.POST.get('selling_price')

            try:
                product = Product.objects.get(id=product_id)
                quantity = Decimal(quantity)
                selling_price = Decimal(selling_price) if selling_price else product.selling_price

                # Create invoice item - the save() method will calculate totals
                SaleInvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity,
                    original_price=product.selling_price,
                    negotiated_price=selling_price,
                    unit_price=selling_price,
                    total_amount=selling_price * quantity
                )

                # Explicitly recalculate totals after item is saved
                invoice.calculate_totals()

                messages.success(request, f"Article {product.reference} ajouté.")

            except Product.DoesNotExist:
                messages.error(request, "Produit non trouvé.")
            except (ValueError, InvalidOperation):
                messages.error(request, "Valeurs invalides.")

        elif action == 'remove_item':
            item_id = request.POST.get('item_id')
            try:
                item = SaleInvoiceItem.objects.get(id=item_id, invoice=invoice)
                item.delete()
                invoice.calculate_totals()
                messages.success(request, "Article retiré.")
            except SaleInvoiceItem.DoesNotExist:
                messages.error(request, "Article non trouvé.")

        elif action == 'complete':
            # Validate invoice has items
            if not invoice.items.exists():
                messages.error(request, "Ajoutez au moins un article avant de valider.")
            else:
                invoice.date = timezone.now().date()

                # Handle custom reference update
                custom_reference = request.POST.get('custom_reference', '').strip()
                if custom_reference and custom_reference != invoice.reference:
                    # Check if new reference already exists
                    if SaleInvoice.objects.filter(reference=custom_reference).exclude(id=invoice.id).exists():
                        messages.error(request, f"La référence '{custom_reference}' existe déjà. Veuillez en choisir une autre.")
                        return redirect('sales:pending_invoice_complete', reference=reference)
                    invoice.reference = custom_reference

                # Set client if provided
                client_id = request.POST.get('client_id')
                if client_id:
                    try:
                        invoice.client = Client.objects.get(id=client_id)
                    except Client.DoesNotExist:
                        pass

                # Set payment method
                payment_method_id = request.POST.get('payment_method')
                if payment_method_id:
                    try:
                        payment_method = PaymentMethod.objects.get(id=payment_method_id)
                        invoice.payment_method = payment_method
                    except PaymentMethod.DoesNotExist:
                        pass

                # Set payment reference (check for uniqueness)
                payment_reference = request.POST.get('payment_reference', '').strip()
                if payment_reference:
                    # Check if this payment reference already exists
                    existing = SaleInvoice.objects.filter(
                        payment_reference__iexact=payment_reference
                    ).exclude(id=invoice.id).exists()
                    if existing:
                        messages.error(request, f"La référence de paiement '{payment_reference}' existe déjà.")
                        return redirect('sales:pending_invoice_complete', reference=reference)
                    invoice.payment_reference = payment_reference

                # Set bank account
                bank_account_id = request.POST.get('bank_account')
                if bank_account_id:
                    try:
                        invoice.bank_account = BankAccount.objects.get(id=bank_account_id)
                    except BankAccount.DoesNotExist:
                        pass

                # Calculate totals first
                invoice.calculate_totals()

                # Get amount paid from form
                amount_paid_str = request.POST.get('amount_paid', '0')
                try:
                    amount_paid = Decimal(amount_paid_str)
                except (InvalidOperation, TypeError):
                    amount_paid = Decimal('0')

                # Set payment amounts and determine status based on amount paid
                invoice.amount_paid = amount_paid
                invoice.balance_due = invoice.total_amount - amount_paid

                if amount_paid >= invoice.total_amount:
                    invoice.status = SaleInvoice.Status.PAID
                    invoice.balance_due = Decimal('0')  # Ensure no negative balance
                elif amount_paid > 0:
                    invoice.status = SaleInvoice.Status.PARTIAL_PAID
                else:
                    invoice.status = SaleInvoice.Status.UNPAID

                invoice.save()

                # Mark all products in the invoice as sold
                for item in invoice.items.all():
                    if item.product:
                        item.product.status = 'sold'
                        item.product.save(update_fields=['status'])

                # Log activity
                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='SaleInvoice',
                    object_id=str(invoice.id),
                    object_repr=str(invoice),
                    details={'action': 'completed_draft', 'reference': invoice.reference}
                )

                messages.success(request, f"Facture {invoice.reference} validée avec succès!")
                return redirect('sales:invoice_detail', reference=invoice.reference)

        elif action == 'quick_create_product':
            # Quick product creation
            return _handle_quick_product_creation(request, invoice)

        return redirect('sales:pending_invoice_complete', reference=reference)

    # GET request - show completion form
    # Refresh invoice from database to get latest totals
    invoice.refresh_from_db()

    # Get available products for selection
    available_products = Product.objects.filter(
        status='available'
    ).select_related('category', 'metal_type', 'purity').order_by('-created_at')[:100]

    # Get form options
    categories = ProductCategory.objects.filter(is_active=True)
    metals = MetalType.objects.filter(is_active=True)
    purities = MetalPurity.objects.filter(is_active=True)
    clients = Client.objects.filter(is_active=True).order_by('first_name')
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)

    context = {
        'invoice': invoice,
        'photos': invoice.photos.all(),
        'items': invoice.items.all(),
        'available_products': available_products,
        'categories': categories,
        'metals': metals,
        'purities': purities,
        'clients': clients,
        'payment_methods': payment_methods,
        'bank_accounts': bank_accounts,
    }

    return render(request, 'sales/pending_invoice_complete.html', context)


def _handle_quick_product_creation(request, invoice):
    """Handle quick product creation from pending invoice form"""
    from settings_app.models import ProductCategory, MetalType, MetalPurity
    from products.models import Product as ProductModel

    try:
        category_id = request.POST.get('quick_category')
        metal_type_id = request.POST.get('quick_metal_type')
        purity_id = request.POST.get('quick_purity')
        weight = request.POST.get('quick_weight')
        selling_price_str = request.POST.get('quick_selling_price')

        # Validate required fields
        if not all([category_id, weight, selling_price_str]):
            messages.error(request, "Catégorie, poids et prix de vente sont requis.")
            return redirect('sales:pending_invoice_complete', reference=invoice.reference)

        category = ProductCategory.objects.get(id=category_id)
        metal_type = MetalType.objects.get(id=metal_type_id) if metal_type_id else None
        metal_purity = MetalPurity.objects.get(id=purity_id) if purity_id else None
        weight_decimal = Decimal(weight)
        selling_price = Decimal(selling_price_str)

        # Generate unique reference for the product
        from django.utils import timezone
        today = timezone.now().strftime('%Y%m%d')
        prefix = f"PRD-{category.code if hasattr(category, 'code') and category.code else 'QCK'}-{today}"

        # Find next sequence number
        existing_count = ProductModel.objects.filter(reference__startswith=prefix).count()
        reference = f"{prefix}-{existing_count + 1:04d}"

        # Create product with correct field names
        product = ProductModel.objects.create(
            reference=reference,
            name=f"{category.name} - Création rapide",
            category=category,
            metal_type=metal_type,
            metal_purity=metal_purity,
            gross_weight=weight_decimal,
            net_weight=weight_decimal,
            selling_price=selling_price,
            status='available',
        )

        # Add to invoice with negotiated_price for proper totals calculation
        SaleInvoiceItem.objects.create(
            invoice=invoice,
            product=product,
            quantity=1,
            original_price=selling_price,
            negotiated_price=selling_price,
            unit_price=selling_price,
            total_amount=selling_price
        )

        # Product stays 'available' until invoice is validated
        # Status will change to 'reserved'/'sold' when invoice is completed

        # Recalculate invoice totals - refresh first to get fresh data
        invoice.refresh_from_db()
        invoice.calculate_totals()

        messages.success(request, f"Article {product.reference} créé et ajouté à la facture.")

    except (ProductCategory.DoesNotExist, MetalType.DoesNotExist, MetalPurity.DoesNotExist) as e:
        messages.error(request, f"Catégorie, métal ou pureté non trouvé: {e}")
    except (ValueError, InvalidOperation) as e:
        messages.error(request, f"Valeurs invalides: {e}")
    except Exception as e:
        import traceback
        messages.error(request, f"Erreur lors de la création: {e}")
        # Log the full traceback for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Quick product creation error: {traceback.format_exc()}")

    return redirect('sales:pending_invoice_complete', reference=invoice.reference)


@login_required(login_url='login')
def search_products_api(request):
    """API endpoint to search products for pending invoice completion"""
    try:
        query = request.GET.get('q', '').strip()
        limit = min(int(request.GET.get('limit', 20)), 50)

        if len(query) < 2:
            return JsonResponse({'products': []})

        # Search only AVAILABLE products (disponible)
        products = Product.objects.filter(
            status='available'
        ).filter(
            Q(reference__icontains=query) |
            Q(name__icontains=query) |
            Q(category__name__icontains=query)
        ).select_related('category', 'metal_type', 'metal_purity').order_by('-created_at')[:limit]

        results = []
        for p in products:
            try:
                results.append({
                    'id': p.id,
                    'reference': p.reference or '',
                    'name': p.name or (p.category.name if p.category else 'Produit'),
                    'category': p.category.name if p.category else '',
                    'metal': p.metal_type.name if p.metal_type else '',
                    'purity': p.metal_purity.name if p.metal_purity else '',
                    'weight': str(p.net_weight) if p.net_weight else '',
                    'selling_price': str(p.selling_price) if p.selling_price else '0',
                    'status': p.get_status_display() if p.status else '',
                    'display': f"{p.reference or ''} - {p.category.name if p.category else ''} - {p.selling_price or 0} DH"
                })
            except Exception as item_error:
                # Skip problematic items
                continue

        return JsonResponse({'products': results})
    except Exception as e:
        import traceback
        return JsonResponse({
            'products': [],
            'error': str(e),
            'traceback': traceback.format_exc()
        })
