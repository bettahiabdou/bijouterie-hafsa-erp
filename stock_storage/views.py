"""
Views for Client Stock Storage management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Count, DecimalField, Value
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal

from .models import StockStorageAccount, StockStorageItem
from settings_app.models import Carrier


@login_required
def storage_list(request):
    """List all stock storage accounts"""
    accounts = StockStorageAccount.objects.select_related('client').filter(is_active=True)

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        accounts = accounts.filter(
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query) |
            Q(client__phone__icontains=search_query) |
            Q(client__code__icontains=search_query)
        )

    # Status filter
    status_filter = request.GET.get('status', '')
    accounts_list = list(accounts)
    if status_filter == 'has_waiting':
        accounts_list = [a for a in accounts_list if a.waiting_items > 0]
    elif status_filter == 'all_picked':
        accounts_list = [a for a in accounts_list if a.waiting_items == 0 and a.total_items > 0]

    # Stats
    total_accounts = len(accounts_list)
    total_waiting = sum(a.waiting_items for a in accounts_list)
    total_value = sum(a.total_value_waiting for a in accounts_list)

    paginator = Paginator(accounts_list, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'accounts': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_accounts': total_accounts,
        'total_waiting': total_waiting,
        'total_value': total_value,
    }
    return render(request, 'stock_storage/storage_list.html', context)


@login_required
def storage_detail(request, pk):
    """View stock storage account detail with items"""
    account = get_object_or_404(
        StockStorageAccount.objects.select_related('client'),
        pk=pk
    )

    items = account.items.select_related('invoice', 'product').order_by('-stored_at')

    # Status filter
    status_filter = request.GET.get('status', '')
    if status_filter == 'waiting':
        items = items.filter(status=StockStorageItem.Status.WAITING)
    elif status_filter == 'picked_up':
        items = items.filter(status=StockStorageItem.Status.PICKED_UP)

    paginator = Paginator(items, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'account': account,
        'items': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'carriers': Carrier.objects.filter(is_active=True),
    }
    return render(request, 'stock_storage/storage_detail.html', context)


@login_required
def pickup_item(request, pk):
    """Mark a single item as picked up, with delivery method + tracking.

    - magasin: just mark récupéré (in-store handover).
    - amana / transporteur: mark récupéré AND create a Delivery record so it
      appears in the central Livraisons page and is auto-tracked (AMANA).
    """
    if request.method != 'POST':
        return redirect('stock_storage:detail', pk=pk)

    account = get_object_or_404(StockStorageAccount, pk=pk)
    item_id = request.POST.get('item_id')

    pickup_method = request.POST.get('pickup_method', 'magasin')
    if pickup_method not in dict(StockStorageItem.PickupMethod.choices):
        pickup_method = 'magasin'
    tracking_number = request.POST.get('tracking_number', '').strip()

    carrier = None
    carrier_id = request.POST.get('carrier_id', '')
    if pickup_method == 'transporteur' and carrier_id:
        carrier = Carrier.objects.filter(pk=carrier_id).first()

    try:
        item = StockStorageItem.objects.get(
            pk=item_id, account=account, status=StockStorageItem.Status.WAITING
        )
    except StockStorageItem.DoesNotExist:
        messages.error(request, 'Article non trouvé ou déjà récupéré.')
        return redirect('stock_storage:detail', pk=pk)

    with transaction.atomic():
        item.mark_picked_up(
            request.user,
            pickup_method=pickup_method,
            carrier=carrier,
            tracking_number=tracking_number,
        )

        # For shipped pickups, create a Delivery so it lands in the central
        # tracking system (same as a sale).
        if pickup_method in ('amana', 'transporteur'):
            from sales.models import Delivery
            client = account.client
            Delivery.objects.create(
                invoice=None,
                stock_storage_item=item,
                client_name=client.full_name if client else '',
                client_phone=client.phone if client else '',
                total_amount=item.price or 0,
                delivery_method_type=pickup_method,
                carrier=carrier,
                tracking_number=tracking_number,
                status='pending',
            )

    messages.success(request, f'Article {item.product_reference} marqué comme récupéré.')
    return redirect('stock_storage:detail', pk=pk)


@login_required
def bulk_pickup(request, pk):
    """Mark multiple items as picked up"""
    if request.method != 'POST':
        return redirect('stock_storage:detail', pk=pk)

    account = get_object_or_404(StockStorageAccount, pk=pk)
    item_ids = request.POST.getlist('item_ids')

    if not item_ids:
        messages.error(request, 'Aucun article sélectionné.')
        return redirect('stock_storage:detail', pk=pk)

    count = 0
    with transaction.atomic():
        items = StockStorageItem.objects.filter(
            pk__in=item_ids,
            account=account,
            status=StockStorageItem.Status.WAITING
        )
        for item in items:
            item.mark_picked_up(request.user)
            count += 1

    if count:
        messages.success(request, f'{count} article(s) marqué(s) comme récupéré(s).')
    else:
        messages.error(request, 'Aucun article en attente trouvé.')

    return redirect('stock_storage:detail', pk=pk)


@login_required
def storage_dashboard(request):
    """Dashboard overview for stock storage"""
    all_accounts = StockStorageAccount.objects.select_related('client').filter(is_active=True)
    accounts_list = list(all_accounts)

    total_accounts = len(accounts_list)
    accounts_with_waiting = [a for a in accounts_list if a.waiting_items > 0]
    total_waiting_items = sum(a.waiting_items for a in accounts_list)
    total_value_waiting = sum(a.total_value_waiting for a in accounts_list)

    # Today's pickups
    today = timezone.now().date()
    today_pickups = StockStorageItem.objects.filter(
        picked_up_at__date=today,
        status=StockStorageItem.Status.PICKED_UP
    ).count()

    # Today's new items
    today_stored = StockStorageItem.objects.filter(
        stored_at__date=today
    ).count()

    context = {
        'total_accounts': total_accounts,
        'accounts_with_waiting': len(accounts_with_waiting),
        'total_waiting_items': total_waiting_items,
        'total_value_waiting': total_value_waiting,
        'today_pickups': today_pickups,
        'today_stored': today_stored,
        'top_accounts': sorted(accounts_with_waiting, key=lambda a: a.waiting_items, reverse=True)[:10],
    }
    return render(request, 'stock_storage/storage_dashboard.html', context)
