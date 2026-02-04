"""
Sales management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum, F
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
from .models import SaleInvoice, SaleInvoiceItem, ClientLoan, Layaway
from products.models import Product
from clients.models import Client
from quotes.models import Quote
from users.models import ActivityLog


@login_required(login_url='login')
def invoice_list(request):
    """List all sales invoices with filtering and search"""
    invoices = SaleInvoice.objects.select_related(
        'client', 'seller', 'delivery_method'
    ).prefetch_related('items')

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

    # Statistics
    today = timezone.now().date()
    stats = {
        'today': SaleInvoice.objects.filter(date=today).aggregate(
            total=Sum('total_amount')
        )['total'] or 0,
        'month': SaleInvoice.objects.filter(
            date__year=today.year,
            date__month=today.month
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        'total_invoices': SaleInvoice.objects.count(),
        'total_revenue': SaleInvoice.objects.aggregate(
            total=Sum('total_amount')
        )['total'] or 0,
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

    context = {
        'invoice': invoice,
        'items': invoice.items.all(),
    }

    return render(request, 'sales/invoice_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_create(request):
    """Create a new sales invoice"""
    # Allow staff/admin users to create invoices
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission de créer des factures.')
        return redirect('sales:invoice_list')

    if request.method == 'POST':
        try:
            # Create invoice
            invoice = SaleInvoice.objects.create(
                reference=generate_invoice_reference(),
                date=timezone.now().date(),
                sale_type=request.POST.get('sale_type', 'regular'),
                client_id=request.POST.get('client'),
                seller=request.user,
                status='draft',
                created_by=request.user,
            )

            # Add items from form
            items_data = request.POST.getlist('items')
            for item_id in items_data:
                product_id = request.POST.get(f'product_{item_id}')
                quantity = request.POST.get(f'quantity_{item_id}', 1)
                unit_price = request.POST.get(f'unit_price_{item_id}')

                if product_id and unit_price:
                    product = Product.objects.get(id=product_id)
                    SaleInvoiceItem.objects.create(
                        invoice=invoice,
                        product=product,
                        unit_price=Decimal(unit_price),
                        original_price=product.selling_price,
                    )

                    # Update product status
                    product.status = 'sold'
                    product.save()

            # Calculate totals
            invoice.calculate_totals()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                action=ActivityLog.ActionType.CREATE,
                model_name='SaleInvoice',
                object_id=str(invoice.id),
                object_repr=invoice.reference,
                ip_address=get_client_ip(request)
            )

            messages.success(request, f'Facture "{invoice.reference}" créée avec succès.')
            return redirect('sales:invoice_detail', reference=invoice.reference)

        except Exception as e:
            messages.error(request, f'Erreur lors de la création: {str(e)}')

    context = {
        'clients': Client.objects.filter(is_active=True),
        'products': Product.objects.filter(status='available'),
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
