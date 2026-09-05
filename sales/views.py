"""
Sales management views for Bijouterie Hafsa ERP
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count, Sum, F
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from .models import (
    SaleInvoice, SaleInvoiceItem, SaleInvoiceAction, ClientLoan, Layaway,
    ProductCirculation,
)
from products.models import Product
from clients.models import Client
from quotes.models import Quote
from users.models import ActivityLog
from settings_app.models import PaymentMethod, BankAccount


@login_required(login_url='login')
def sales_insights(request):
    """AI-powered business insights page with computed metrics. AI loads async via AJAX."""
    import json
    from ai_services.business_insights import gather_business_data, gather_decision_intelligence, gather_dashboard, DecimalEncoder
    from .models import SalesTarget

    # Save editable targets
    if request.method == 'POST' and request.POST.get('action') == 'save_targets':
        from decimal import Decimal, InvalidOperation
        def _num(v, default):
            try:
                return Decimal(str(v).replace(',', '.'))
            except (InvalidOperation, ValueError, TypeError):
                return default
        SalesTarget.objects.create(
            revenue_target=_num(request.POST.get('revenue_target'), Decimal('0')),
            margin_target=_num(request.POST.get('margin_target'), Decimal('18')),
            new_clients_target=int(request.POST.get('new_clients_target') or 0),
        )
        messages.success(request, 'Objectifs mis à jour.')
        return redirect(f"{request.path}?period={request.GET.get('period', 'all')}")

    period = request.GET.get('period', 'all')
    period_map = {'7d': 7, '30d': 30, '90d': 90, 'all': None}
    period_days = period_map.get(period)

    data = gather_business_data(period_days=period_days)
    intel = gather_decision_intelligence(period_days=period_days)
    dash = gather_dashboard(period_days=period_days)

    # Prepare chart data as JSON
    chart_categories = json.dumps(
        [c['name'] for c in data['categories'][:10]], cls=DecimalEncoder
    )
    chart_cat_revenue = json.dumps(
        [float(c['revenue']) for c in data['categories'][:10]], cls=DecimalEncoder
    )
    chart_cat_items = json.dumps(
        [c['items_sold'] for c in data['categories'][:10]], cls=DecimalEncoder
    )
    chart_daily_labels = json.dumps(
        [d['day'].strftime('%d/%m') for d in data['daily_trend']]
    )
    chart_daily_revenue = json.dumps(
        [float(d['revenue'] or 0) for d in data['daily_trend']]
    )
    chart_sell_through = json.dumps(
        [{'cat': s['category'], 'rate': s['sell_through_pct']} for s in data['sell_through']],
        cls=DecimalEncoder
    )

    context = {
        'data': data,
        'intel': intel,
        'dash': dash,
        'period': period,
        'chart_categories': chart_categories,
        'chart_cat_revenue': chart_cat_revenue,
        'chart_cat_items': chart_cat_items,
        'chart_daily_labels': chart_daily_labels,
        'chart_daily_revenue': chart_daily_revenue,
        'chart_sell_through': chart_sell_through,
    }
    return render(request, 'sales/insights.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def sales_insights_ai(request):
    """AJAX endpoint: generate AI recommendations (can take 30-60s)."""
    import json
    import logging
    from django.core.cache import cache
    from ai_services.business_insights import gather_business_data, gather_decision_intelligence, generate_ai_insights

    logger = logging.getLogger(__name__)

    period = request.GET.get('period', 'all')
    period_map = {'7d': 7, '30d': 30, '90d': 90, 'all': None}
    period_days = period_map.get(period)
    refresh = request.GET.get('refresh') == '1'

    cache_key = f'business_insights_{period}_{timezone.now().date()}'
    ai_insights = cache.get(cache_key)

    if not ai_insights or refresh:
        try:
            data = gather_business_data(period_days=period_days)
            data['decision_intel'] = gather_decision_intelligence(period_days=period_days)
            ai_insights = generate_ai_insights(data)
            if ai_insights:
                cache.set(cache_key, ai_insights, 3600 * 6)
        except Exception as e:
            logger.error(f'AI insights generation failed: {e}')
            return JsonResponse({'error': str(e)}, status=500)

    if not ai_insights:
        return JsonResponse({'error': 'Aucune réponse de l\'IA'}, status=500)

    # Parse into sections
    sections = []
    current_section = None
    current_content = []
    for line in ai_insights.split('\n'):
        stripped = line.strip()
        if stripped.startswith('**') and stripped.endswith('**') and any(kw in stripped.upper() for kw in ['INVESTISSEMENT', 'MARKETING', 'PRIX', 'FIDÉLISATION', 'FIDELISATION', 'ALERTE', 'ACTION', 'OPPORTUN', 'ANOMAL', 'SIGNAL', 'ACQUISITION', 'RÉTENTION', 'RETENTION', 'STOCK', 'ACHAT', 'DÉCISION', 'DECISION']):
            if current_section:
                sections.append({'title': current_section, 'content': '\n'.join(current_content)})
            current_section = stripped.strip('*').strip()
            current_content = []
        elif stripped.startswith('## ') or stripped.startswith('# '):
            if current_section:
                sections.append({'title': current_section, 'content': '\n'.join(current_content)})
            current_section = stripped.lstrip('#').strip().strip('*').strip()
            current_content = []
        else:
            current_content.append(line)
    if current_section:
        sections.append({'title': current_section, 'content': '\n'.join(current_content)})

    return JsonResponse({'sections': sections, 'raw': ai_insights})


@login_required(login_url='login')
def sales_dashboard(request):
    """Comprehensive sales dashboard with full payment analytics"""
    from django.db.models import Avg, Min, Max, Subquery, OuterRef, Value, Case, When, DecimalField as DjDecimalField
    from django.db.models.functions import TruncDate, TruncMonth, Coalesce
    from django.contrib.auth import get_user_model
    from payments.models import ClientPayment
    from .models import Delivery
    from datetime import timedelta
    import json
    User = get_user_model()

    today = timezone.now().date()
    current_month_start = today.replace(day=1)

    # ============ FILTERS ============
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    seller_filter = request.GET.get('seller', '')
    period_filter = request.GET.get('period', 'month')  # today, month, all

    # Base queryset - exclude deleted, returned, cancelled, exchanged, and drafts
    base_qs = SaleInvoice.objects.filter(is_deleted=False).exclude(
        status__in=['returned', 'cancelled', 'draft', 'exchanged']
    )

    # Apply date filters
    if date_from:
        base_qs = base_qs.filter(date__gte=date_from)
    elif period_filter == 'today':
        base_qs = base_qs.filter(date=today)
    elif period_filter == 'month':
        base_qs = base_qs.filter(date__gte=current_month_start)

    if date_to:
        base_qs = base_qs.filter(date__lte=date_to)

    if seller_filter:
        base_qs = base_qs.filter(seller_id=seller_filter)

    # ============ MAIN STATS ============
    # Weight computed separately to avoid JOIN inflation on other fields
    filtered_stats = base_qs.aggregate(
        revenue=Sum('total_amount'),
        count=Count('id'),
        paid=Sum('amount_paid'),
        balance=Sum('balance_due'),
        discount=Sum('discount_amount'),
        old_gold=Sum('old_gold_amount'),
    )
    filtered_stats['weight'] = base_qs.aggregate(
        weight=Sum('items__product__gross_weight')
    )['weight']
    filtered_invoice_ids = list(base_qs.values_list('id', flat=True))

    # ============ REFUNDS (returns) IN PERIOD ============
    # Returns on invoices still in the active set reduce revenue (any refund method)
    # and encaissement (cash refunds only). Fully-returned invoices are already
    # excluded from base_qs, so their refunds are NOT double-counted here.
    _period_returns = SaleInvoiceAction.objects.filter(
        action_type=SaleInvoiceAction.ActionType.RETURN,
        original_invoice__in=base_qs,
    )
    period_refund_total = _period_returns.aggregate(t=Sum('refund_amount'))['t'] or Decimal('0')
    period_cash_refund_total = _period_returns.filter(
        refund_method='cash'
    ).aggregate(t=Sum('refund_amount'))['t'] or Decimal('0')

    # ============ DELIVERY TYPE BREAKDOWN ============
    magasin_qs = base_qs.filter(Q(delivery_method_type='magasin') | Q(delivery_method_type__isnull=True) | Q(delivery_method_type=''))
    amana_qs = base_qs.filter(delivery_method_type='amana')
    transporteur_qs = base_qs.filter(delivery_method_type='transporteur')
    en_stock_qs = base_qs.filter(delivery_method_type='en_stock')

    magasin_stats = magasin_qs.aggregate(revenue=Sum('total_amount'), count=Count('id'))
    amana_stats = amana_qs.aggregate(revenue=Sum('total_amount'), count=Count('id'))
    transporteur_stats = transporteur_qs.aggregate(revenue=Sum('total_amount'), count=Count('id'))
    en_stock_stats = en_stock_qs.aggregate(revenue=Sum('total_amount'), count=Count('id'))

    # ============ PAYMENT DATE FILTER ============
    payment_date_filter = {}
    if date_from:
        payment_date_filter['date__gte'] = date_from
    elif period_filter == 'today':
        payment_date_filter['date'] = today
    elif period_filter == 'month':
        payment_date_filter['date__gte'] = current_month_start
    if date_to:
        payment_date_filter['date__lte'] = date_to

    # ============ ALL PAYMENTS FOR PERIOD ============
    # Payments are filtered by PAYMENT DATE only (not invoice date)
    # so that a sale on date X with payment on date Y shows payment on Y
    period_payments_qs = ClientPayment.objects.filter(
        sale_invoice__is_deleted=False,
        **payment_date_filter,
    ).exclude(sale_invoice__status='returned')
    if seller_filter:
        period_payments_qs = period_payments_qs.filter(sale_invoice__seller_id=seller_filter)

    all_payments_total = period_payments_qs.exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    deposit_client_total = period_payments_qs.filter(
        payment_method__name='Dépôt Client',
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # AMANA not received
    amana_not_received = period_payments_qs.filter(
        sale_invoice__delivery_method_type='amana',
    ).exclude(
        sale_invoice__delivery__status='delivered'
    ).exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Transporteur not received
    transporteur_not_received = period_payments_qs.filter(
        sale_invoice__delivery_method_type='transporteur',
    ).exclude(
        sale_invoice__delivery__status='delivered'
    ).exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    total_delivery_pending = amana_not_received + transporteur_not_received
    # Cash refunds reduce real cash collected; deposit-credit refunds do not.
    real_encaisse = all_payments_total - total_delivery_pending - period_cash_refund_total

    # ============ DETAILED PAYMENT BREAKDOWN: Method + Bank ============
    # Group by payment_method AND bank_account for full detail
    payment_method_breakdown = list(
        period_payments_qs.values(
            'payment_method__name'
        ).annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('-total')
    )

    # Payment by method + bank (every method, including Dépôt Client which gets
    # its own card in the detail — it stays out of the encaissement total above).
    payment_by_method_bank = list(
        period_payments_qs.values(
            'payment_method__name',
            'bank_account__bank_name',
            'bank_account__id',
        ).annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('payment_method__name', '-total')
    )

    # Structure: { method_name: { total, count, banks: [{bank_name, total, count}] } }
    payment_detail = {}
    for row in payment_by_method_bank:
        method = row['payment_method__name'] or 'Non défini'
        bank = row['bank_account__bank_name'] or None
        if method not in payment_detail:
            payment_detail[method] = {'total': Decimal('0'), 'count': 0, 'banks': [], 'invoices': []}
        payment_detail[method]['total'] += row['total']
        payment_detail[method]['count'] += row['count']
        if bank:
            payment_detail[method]['banks'].append({
                'bank_name': bank,
                'bank_id': row['bank_account__id'],
                'total': row['total'],
                'count': row['count'],
            })

    # Sort by total descending
    payment_detail_sorted = sorted(payment_detail.items(), key=lambda x: x[1]['total'], reverse=True)

    # ============ PER-INVOICE DETAIL FOR EACH PAYMENT METHOD ============
    # Get all individual payments with their invoice info
    payment_invoices_raw = list(
        period_payments_qs.select_related(
            'sale_invoice', 'sale_invoice__client', 'payment_method', 'bank_account'
        ).order_by('payment_method__name', '-date', '-amount')
    )

    # Group invoices by payment method
    payment_invoices_by_method = {}
    for pay in payment_invoices_raw:
        method = pay.payment_method.name if pay.payment_method else 'Non défini'
        if method not in payment_invoices_by_method:
            payment_invoices_by_method[method] = []
        payment_invoices_by_method[method].append({
            'reference': pay.reference,
            'invoice_ref': pay.sale_invoice.reference if pay.sale_invoice else '—',
            'invoice_id': pay.sale_invoice_id,
            'client': (pay.sale_invoice.client.full_name if pay.sale_invoice and pay.sale_invoice.client else 'Anonyme'),
            'amount': pay.amount,
            'date': pay.date,
            'bank_name': pay.bank_account.bank_name if pay.bank_account else None,
            'check_number': pay.check_number or '',
        })

    # Combine payment_detail with invoices
    payment_sections = []
    for method_name, detail in payment_detail_sorted:
        is_deposit = (method_name or '').strip().lower() in ('dépôt client', 'depot client', 'dépôt')
        section = {
            'method': method_name,
            'total': detail['total'],
            'count': detail['count'],
            'banks': detail['banks'],
            'invoices': payment_invoices_by_method.get(method_name, []),
            'is_deposit': is_deposit,
        }
        payment_sections.append(section)

    # ============ BANK ACCOUNT SUMMARY ============
    bank_summary = list(
        period_payments_qs.exclude(
            payment_method__name='Dépôt Client'
        ).filter(
            bank_account__isnull=False
        ).values(
            'bank_account__id', 'bank_account__bank_name', 'bank_account__account_name'
        ).annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('-total')
    )

    # Bank detail: per-bank, per-method breakdown
    bank_method_detail = list(
        period_payments_qs.exclude(
            payment_method__name='Dépôt Client'
        ).filter(
            bank_account__isnull=False
        ).values(
            'bank_account__bank_name',
            'payment_method__name',
        ).annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('bank_account__bank_name', '-total')
    )

    # Group: { bank_name: { total, methods: [{method, total, count}], payments: [...] } }
    bank_detail_grouped = {}
    for row in bank_method_detail:
        bank = row['bank_account__bank_name']
        if bank not in bank_detail_grouped:
            bank_detail_grouped[bank] = {'total': Decimal('0'), 'count': 0, 'methods': [], 'payments': []}
        bank_detail_grouped[bank]['total'] += row['total']
        bank_detail_grouped[bank]['count'] += row['count']
        bank_detail_grouped[bank]['methods'].append({
            'method': row['payment_method__name'],
            'total': row['total'],
            'count': row['count'],
        })

    # Per-bank individual payments
    bank_payments_raw = list(
        period_payments_qs.exclude(
            payment_method__name='Dépôt Client'
        ).filter(
            bank_account__isnull=False
        ).select_related(
            'sale_invoice', 'sale_invoice__client', 'payment_method', 'bank_account'
        ).order_by('bank_account__bank_name', 'payment_method__name', '-date')
    )
    for pay in bank_payments_raw:
        bank = pay.bank_account.bank_name
        if bank in bank_detail_grouped:
            bank_detail_grouped[bank]['payments'].append({
                'invoice_ref': pay.sale_invoice.reference if pay.sale_invoice else '—',
                'client': (pay.sale_invoice.client.full_name if pay.sale_invoice and pay.sale_invoice.client else 'Anonyme'),
                'amount': pay.amount,
                'date': pay.date,
                'method': pay.payment_method.name if pay.payment_method else '—',
                'check_number': pay.check_number or '',
            })

    # Also get payments WITHOUT a bank account (e.g. Espèces/cash)
    no_bank_payments_raw = list(
        period_payments_qs.exclude(
            payment_method__name='Dépôt Client'
        ).filter(
            bank_account__isnull=True
        ).select_related(
            'sale_invoice', 'sale_invoice__client', 'payment_method'
        ).order_by('payment_method__name', '-date')
    )
    if no_bank_payments_raw:
        no_bank_total = sum(p.amount for p in no_bank_payments_raw)
        no_bank_methods = {}
        no_bank_pays = []
        for pay in no_bank_payments_raw:
            m = pay.payment_method.name if pay.payment_method else 'Autre'
            if m not in no_bank_methods:
                no_bank_methods[m] = {'method': m, 'total': Decimal('0'), 'count': 0}
            no_bank_methods[m]['total'] += pay.amount
            no_bank_methods[m]['count'] += 1
            no_bank_pays.append({
                'invoice_ref': pay.sale_invoice.reference if pay.sale_invoice else '—',
                'client': (pay.sale_invoice.client.full_name if pay.sale_invoice and pay.sale_invoice.client else 'Anonyme'),
                'amount': pay.amount,
                'date': pay.date,
                'method': m,
                'check_number': pay.check_number or '',
            })
        bank_detail_grouped['Sans Banque (Especes, etc.)'] = {
            'total': no_bank_total,
            'count': len(no_bank_payments_raw),
            'methods': list(no_bank_methods.values()),
            'payments': no_bank_pays,
        }

    bank_detail_sorted = sorted(bank_detail_grouped.items(), key=lambda x: x[1]['total'], reverse=True)

    # ============ INVOICE LISTS PER DELIVERY TYPE ============
    magasin_invoices = list(
        magasin_qs.select_related('client', 'seller', 'payment_method')
        .order_by('-date')[:30]
    )
    amana_invoices_all = list(
        amana_qs.select_related('client', 'seller', 'delivery')
        .order_by('-date')[:30]
    )
    transporteur_invoices_all = list(
        transporteur_qs.select_related('client', 'seller', 'delivery', 'carrier')
        .order_by('-date')[:30]
    )

    # ============ TODAY KPIs ============
    today_base = SaleInvoice.objects.filter(is_deleted=False, date=today).exclude(
        status__in=['returned', 'cancelled', 'draft', 'exchanged']
    )
    if seller_filter:
        today_base = today_base.filter(seller_id=seller_filter)

    today_stats_raw = today_base.aggregate(
        revenue=Sum('total_amount'),
        count=Count('id'),
    )
    today_stats_raw['weight'] = today_base.aggregate(
        weight=Sum('items__product__gross_weight')
    )['weight']
    today_invoice_ids = list(today_base.values_list('id', flat=True))

    # Today's refunds on still-active invoices
    _today_returns = SaleInvoiceAction.objects.filter(
        action_type=SaleInvoiceAction.ActionType.RETURN,
        original_invoice__in=today_base,
    )
    today_refund_total = _today_returns.aggregate(t=Sum('refund_amount'))['t'] or Decimal('0')
    today_cash_refund_total = _today_returns.filter(
        refund_method='cash'
    ).aggregate(t=Sum('refund_amount'))['t'] or Decimal('0')

    # Today payments: filter by PAYMENT DATE only (not invoice date)
    today_payments_base = ClientPayment.objects.filter(
        date=today,
        sale_invoice__is_deleted=False,
    ).exclude(sale_invoice__status='returned')
    if seller_filter:
        today_payments_base = today_payments_base.filter(sale_invoice__seller_id=seller_filter)

    today_all_payments = today_payments_base.exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    today_amana_pending = today_payments_base.filter(
        sale_invoice__delivery_method_type='amana',
    ).exclude(sale_invoice__delivery__status='delivered').exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    today_transporteur_pending = today_payments_base.filter(
        sale_invoice__delivery_method_type='transporteur',
    ).exclude(sale_invoice__delivery__status='delivered').exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    today_delivery_pending = today_amana_pending + today_transporteur_pending
    today_encaisse = today_all_payments - today_delivery_pending - today_cash_refund_total

    # Today payment method breakdown
    today_payment_methods = list(
        today_payments_base.exclude(
            payment_method__name='Dépôt Client'
        ).values(
            'payment_method__name',
        ).annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('-total')
    )

    # ============ DELIVERY PENDING (GLOBAL) ============
    amana_pending_invoices = SaleInvoice.objects.filter(
        is_deleted=False, delivery_method_type='amana',
    ).exclude(status='returned').exclude(
        delivery__status='delivered'
    ).select_related('client', 'seller', 'delivery').order_by('-date')

    amana_pending_list = []
    amana_pending_total = Decimal('0')
    for inv in amana_pending_invoices[:50]:
        inv_amount = inv.total_amount or Decimal('0')
        if inv_amount > 0:
            amana_pending_list.append({'invoice': inv, 'amount': inv_amount})
            amana_pending_total += inv_amount

    transporteur_pending_invoices = SaleInvoice.objects.filter(
        is_deleted=False, delivery_method_type='transporteur',
    ).exclude(status='returned').exclude(
        delivery__status='delivered'
    ).select_related('client', 'seller', 'delivery', 'carrier').order_by('-date')

    transporteur_pending_list = []
    transporteur_pending_total = Decimal('0')
    for inv in transporteur_pending_invoices[:50]:
        inv_amount = inv.total_amount or Decimal('0')
        if inv_amount > 0:
            transporteur_pending_list.append({'invoice': inv, 'amount': inv_amount})
            transporteur_pending_total += inv_amount

    # ============ PAYMENT STATUS BREAKDOWN ============
    status_breakdown = list(
        base_qs.values('status')
        .annotate(count=Count('id'), total=Sum('total_amount'), paid=Sum('amount_paid'))
        .order_by('status')
    )

    # ============ ITEMS QUERYSET (used by seller, metal, category breakdowns) ============
    items_qs = SaleInvoiceItem.objects.filter(
        invoice__in=base_qs, is_returned=False
    )

    # ============ SELLER PERFORMANCE (enhanced with per-metal prix/g) ============
    # Revenue/count without JOIN inflation
    seller_invoice_stats = list(
        base_qs.values('seller__id', 'seller__first_name', 'seller__last_name', 'seller__username')
        .annotate(
            count=Count('id'), revenue=Sum('total_amount'),
            paid=Sum('amount_paid'), balance=Sum('balance_due'),
            discount=Sum('discount_amount'),
            subtotal=Sum('subtotal'),
        ).order_by('-revenue')
    )
    # Per-seller per-metal stats from items
    seller_metal_raw = list(items_qs.filter(
        product__metal_type__isnull=False
    ).values(
        'invoice__seller__id',
        'product__metal_type__name',
    ).annotate(
        weight=Sum('product__gross_weight'),
        revenue=Sum('total_amount'),
    ).order_by('invoice__seller__id', '-revenue'))
    # Build map: seller_id -> [{name, weight, revenue, prix_g}]
    from collections import defaultdict
    seller_metal_map = defaultdict(list)
    for sm in seller_metal_raw:
        w = sm['weight'] or Decimal('0')
        rev = sm['revenue'] or Decimal('0')
        seller_metal_map[sm['invoice__seller__id']].append({
            'name': sm['product__metal_type__name'],
            'weight': w,
            'revenue': rev,
            'prix_g': (rev / w).quantize(Decimal('0.01')) if w > 0 else Decimal('0'),
        })
    # Merge
    seller_stats = []
    for s in seller_invoice_stats:
        sid = s['seller__id']
        sub = s['subtotal'] or Decimal('0')
        disc = s['discount'] or Decimal('0')
        s['discount_pct'] = (disc / sub * 100).quantize(Decimal('0.1')) if sub > 0 else Decimal('0')
        s['metals'] = seller_metal_map.get(sid, [])
        seller_stats.append(s)

    today_seller_base = SaleInvoice.objects.filter(is_deleted=False, date=today).exclude(
        status__in=['returned', 'cancelled', 'draft']
    )
    # Today seller stats
    today_seller_invoice = list(
        today_seller_base
        .values('seller__id', 'seller__first_name', 'seller__last_name', 'seller__username')
        .annotate(count=Count('id'), revenue=Sum('total_amount'))
        .order_by('-revenue')
    )
    today_items_for_sellers = SaleInvoiceItem.objects.filter(
        invoice__in=today_seller_base, is_returned=False
    )
    today_seller_metal_raw = list(today_items_for_sellers.filter(
        product__metal_type__isnull=False
    ).values(
        'invoice__seller__id',
        'product__metal_type__name',
    ).annotate(
        weight=Sum('product__gross_weight'),
        revenue=Sum('total_amount'),
    ).order_by('invoice__seller__id', '-revenue'))
    today_seller_metal_map = defaultdict(list)
    for sm in today_seller_metal_raw:
        w = sm['weight'] or Decimal('0')
        rev = sm['revenue'] or Decimal('0')
        today_seller_metal_map[sm['invoice__seller__id']].append({
            'name': sm['product__metal_type__name'],
            'weight': w,
            'revenue': rev,
            'prix_g': (rev / w).quantize(Decimal('0.01')) if w > 0 else Decimal('0'),
        })
    seller_stats_today = []
    for s in today_seller_invoice:
        sid = s['seller__id']
        s['metals'] = today_seller_metal_map.get(sid, [])
        seller_stats_today.append(s)

    # ============ METAL TYPE BREAKDOWN ============
    from settings_app.models import MetalType
    metal_breakdown_raw = list(items_qs.filter(
        product__metal_type__isnull=False
    ).values('product__metal_type__name').annotate(
        item_count=Count('id'),
        gross_weight=Sum('product__gross_weight'),
        net_weight=Sum('product__net_weight'),
        revenue=Sum('total_amount'),
    ).order_by('-revenue'))
    total_items_revenue = sum(m['revenue'] or Decimal('0') for m in metal_breakdown_raw) or Decimal('1')
    metal_breakdown = []
    for m in metal_breakdown_raw:
        gw = m['gross_weight'] or Decimal('0')
        nw = m['net_weight'] or Decimal('0')
        rev = m['revenue'] or Decimal('0')
        m['prix_g_gross'] = (rev / gw).quantize(Decimal('0.01')) if gw > 0 else Decimal('0')
        m['prix_g_net'] = (rev / nw).quantize(Decimal('0.01')) if nw > 0 else Decimal('0')
        m['pct_revenue'] = (rev / total_items_revenue * 100).quantize(Decimal('0.1'))
        metal_breakdown.append(m)

    # ============ CATEGORY BREAKDOWN ============
    category_breakdown_raw = list(items_qs.filter(
        product__category__isnull=False
    ).values('product__category__name').annotate(
        item_count=Count('id'),
        gross_weight=Sum('product__gross_weight'),
        revenue=Sum('total_amount'),
    ).order_by('-revenue'))
    # Per-category per-metal stats
    cat_metal_raw = list(items_qs.filter(
        product__category__isnull=False,
        product__metal_type__isnull=False,
    ).values(
        'product__category__name',
        'product__metal_type__name',
    ).annotate(
        weight=Sum('product__gross_weight'),
        revenue=Sum('total_amount'),
    ).order_by('product__category__name', '-revenue'))
    cat_metal_map = defaultdict(list)
    for cm in cat_metal_raw:
        w = cm['weight'] or Decimal('0')
        rev = cm['revenue'] or Decimal('0')
        cat_metal_map[cm['product__category__name']].append({
            'name': cm['product__metal_type__name'],
            'weight': w,
            'revenue': rev,
            'prix_g': (rev / w).quantize(Decimal('0.01')) if w > 0 else Decimal('0'),
        })
    category_breakdown = []
    for c in category_breakdown_raw:
        gw = c['gross_weight'] or Decimal('0')
        rev = c['revenue'] or Decimal('0')
        c['prix_g'] = (rev / gw).quantize(Decimal('0.01')) if gw > 0 else Decimal('0')
        c['pct_revenue'] = (rev / total_items_revenue * 100).quantize(Decimal('0.1'))
        c['metals'] = cat_metal_map.get(c['product__category__name'], [])
        category_breakdown.append(c)

    # ============ PER-METAL PRIX/G KPI CARDS ============
    # For period section - compact list of {name, weight, revenue, prix_g}
    metal_prix_g = []
    for m in metal_breakdown:
        gw = m['gross_weight'] or Decimal('0')
        rev = m['revenue'] or Decimal('0')
        metal_prix_g.append({
            'name': m['product__metal_type__name'],
            'weight': gw,
            'revenue': rev,
            'prix_g': (rev / gw).quantize(Decimal('0.01')) if gw > 0 else Decimal('0'),
        })

    # For today section - same but from today's items
    today_items_qs = SaleInvoiceItem.objects.filter(
        invoice__in=today_base, is_returned=False
    )
    today_metal_raw = list(today_items_qs.filter(
        product__metal_type__isnull=False
    ).values('product__metal_type__name').annotate(
        gross_weight=Sum('product__gross_weight'),
        revenue=Sum('total_amount'),
    ).order_by('-revenue'))
    today_metal_prix_g = []
    for m in today_metal_raw:
        gw = m['gross_weight'] or Decimal('0')
        rev = m['revenue'] or Decimal('0')
        today_metal_prix_g.append({
            'name': m['product__metal_type__name'],
            'weight': gw,
            'revenue': rev,
            'prix_g': (rev / gw).quantize(Decimal('0.01')) if gw > 0 else Decimal('0'),
        })

    # ============ DAILY REVENUE (last 30 days) ============
    thirty_days_ago = today - timedelta(days=30)
    daily_base = SaleInvoice.objects.filter(is_deleted=False, date__gte=thirty_days_ago).exclude(
        status__in=['returned', 'cancelled', 'draft', 'exchanged']
    )
    if seller_filter:
        daily_base = daily_base.filter(seller_id=seller_filter)
    daily_revenue = list(
        daily_base.annotate(day=TruncDate('date')).values('day')
        .annotate(revenue=Sum('total_amount'), count=Count('id'))
        .order_by('day')
    )

    # ============ DAILY ENCAISSE (last 30 days) for chart ============
    daily_payments_raw = list(
        ClientPayment.objects.filter(
            date__gte=thirty_days_ago,
            sale_invoice__is_deleted=False,
        ).exclude(
            payment_method__name='Dépôt Client'
        ).exclude(
            sale_invoice__status__in=['returned', 'exchanged']
        ).annotate(day=TruncDate('date')).values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    daily_payments_map = {str(d['day']): float(d['total']) for d in daily_payments_raw}

    # Build chart data JSON
    chart_labels = []
    chart_revenue = []
    chart_encaisse = []
    chart_counts = []
    for d in daily_revenue:
        day_str = str(d['day'])
        chart_labels.append(d['day'].strftime('%d/%m'))
        chart_revenue.append(float(d['revenue'] or 0))
        chart_encaisse.append(daily_payments_map.get(day_str, 0))
        chart_counts.append(d['count'])

    # Payment method chart data
    pm_chart_labels = []
    pm_chart_values = []
    for pm in payment_method_breakdown:
        if pm['payment_method__name'] != 'Dépôt Client':
            pm_chart_labels.append(pm['payment_method__name'] or 'Autre')
            pm_chart_values.append(float(pm['total']))

    # Delivery type chart data
    dt_chart_labels = ['Magasin', 'AMANA', 'Transporteur', 'En Stock']
    dt_chart_values = [
        float(magasin_stats['revenue'] or 0),
        float(amana_stats['revenue'] or 0),
        float(transporteur_stats['revenue'] or 0),
        float(en_stock_stats['revenue'] or 0),
    ]

    # ============ DELIVERY STATUS OVERVIEW ============
    delivery_stats = list(
        Delivery.objects.values('status')
        .annotate(count=Count('id'), total=Sum('total_amount'))
        .order_by('status')
    )

    # ============ TOP INVOICES ============
    recent_large = base_qs.select_related('client', 'seller').order_by('-total_amount')[:10]

    # ============ SELLERS LIST FOR FILTER ============
    sellers = User.objects.filter(sales__isnull=False).distinct().order_by('first_name', 'last_name')

    # ============ DEPOSIT FUNDS RECEIVED (separate from sales) ============
    from deposits.models import DepositTransaction
    deposit_date_filter = {}
    if date_from:
        deposit_date_filter['date__gte'] = date_from
    elif period_filter == 'today':
        deposit_date_filter['date'] = today
    elif period_filter == 'month':
        deposit_date_filter['date__gte'] = current_month_start
    if date_to:
        deposit_date_filter['date__lte'] = date_to

    deposit_funds_total = DepositTransaction.objects.filter(
        transaction_type='deposit',
        **deposit_date_filter,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    today_deposit_funds = DepositTransaction.objects.filter(
        transaction_type='deposit',
        date=today,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Revenue (CA) is reduced by the refunded amount (any method) for returns in period
    filter_revenue = (filtered_stats['revenue'] or Decimal('0')) - period_refund_total
    filter_weight = filtered_stats['weight'] or Decimal('0')

    # ============ RETURNS / REFUNDS VISIBILITY (by return date) ============
    returns_period_qs = SaleInvoiceAction.objects.filter(
        action_type=SaleInvoiceAction.ActionType.RETURN
    )
    if date_from:
        returns_period_qs = returns_period_qs.filter(created_at__date__gte=date_from)
    elif period_filter == 'today':
        returns_period_qs = returns_period_qs.filter(created_at__date=today)
    elif period_filter == 'month':
        returns_period_qs = returns_period_qs.filter(created_at__date__gte=current_month_start)
    if date_to:
        returns_period_qs = returns_period_qs.filter(created_at__date__lte=date_to)
    if seller_filter:
        returns_period_qs = returns_period_qs.filter(original_invoice__seller_id=seller_filter)

    returns_agg = returns_period_qs.aggregate(
        count=Count('id'),
        total=Sum('refund_amount'),
        cash=Sum('refund_amount', filter=Q(refund_method='cash')),
        deposit=Sum('refund_amount', filter=Q(refund_method='deposit')),
    )
    recent_returns = list(
        returns_period_qs.select_related('original_invoice', 'deposit_client', 'created_by')
        .order_by('-created_at')[:20]
    )

    context = {
        'today': today,
        'date_from': date_from,
        'date_to': date_to,
        'seller_filter': seller_filter,
        'period_filter': period_filter,
        'sellers': sellers,
        # Today
        'today_stats': {
            'revenue': (today_stats_raw['revenue'] or Decimal('0')) - today_refund_total,
            'encaisse': today_encaisse,
            'amana_pending': today_amana_pending,
            'transporteur_pending': today_transporteur_pending,
            'count': today_stats_raw['count'] or 0,
            'weight': today_stats_raw['weight'] or Decimal('0'),
            'deposit_funds': today_deposit_funds,
        },
        'today_metal_prix_g': today_metal_prix_g,
        'today_payment_methods': today_payment_methods,
        # Returns / refunds
        'returns_stats': {
            'count': returns_agg['count'] or 0,
            'total': returns_agg['total'] or Decimal('0'),
            'cash': returns_agg['cash'] or Decimal('0'),
            'deposit': returns_agg['deposit'] or Decimal('0'),
        },
        'recent_returns': recent_returns,
        # Period
        'period_stats': {
            'revenue': filter_revenue,
            'encaisse': real_encaisse,
            'deposit_funds': deposit_funds_total,
            'amana_pending': amana_not_received,
            'transporteur_pending': transporteur_not_received,
            'count': filtered_stats['count'] or 0,
            'weight': filtered_stats['weight'] or Decimal('0'),
            'paid': filtered_stats['paid'] or Decimal('0'),
            'balance': filtered_stats['balance'] or Decimal('0'),
            'discount': filtered_stats['discount'] or Decimal('0'),
            'old_gold': filtered_stats['old_gold'] or Decimal('0'),
        },
        # Delivery type
        'magasin_stats': {'revenue': magasin_stats['revenue'] or Decimal('0'), 'count': magasin_stats['count'] or 0},
        'amana_stats': {'revenue': amana_stats['revenue'] or Decimal('0'), 'count': amana_stats['count'] or 0},
        'transporteur_stats': {'revenue': transporteur_stats['revenue'] or Decimal('0'), 'count': transporteur_stats['count'] or 0},
        'en_stock_stats': {'revenue': en_stock_stats['revenue'] or Decimal('0'), 'count': en_stock_stats['count'] or 0},
        # Invoice lists
        'magasin_invoices': magasin_invoices,
        'amana_invoices_all': amana_invoices_all,
        'transporteur_invoices_all': transporteur_invoices_all,
        # Payment detail
        'payment_method_breakdown': payment_method_breakdown,
        'payment_sections': payment_sections,
        'bank_detail_sorted': bank_detail_sorted,
        'bank_summary': bank_summary,
        'deposit_client_total': deposit_client_total,
        'status_breakdown': status_breakdown,
        # Pending
        'amana_pending_list': amana_pending_list,
        'amana_pending_total': amana_pending_total,
        'amana_pending_count': len(amana_pending_list),
        'transporteur_pending_list': transporteur_pending_list,
        'transporteur_pending_total': transporteur_pending_total,
        'transporteur_pending_count': len(transporteur_pending_list),
        # Sellers
        'seller_stats': seller_stats,
        'seller_stats_today': seller_stats_today,
        # Breakdowns
        'metal_breakdown': metal_breakdown,
        'category_breakdown': category_breakdown,
        'metal_prix_g': metal_prix_g,
        # Charts
        'daily_revenue': daily_revenue,
        'chart_labels_json': json.dumps(chart_labels),
        'chart_revenue_json': json.dumps(chart_revenue),
        'chart_encaisse_json': json.dumps(chart_encaisse),
        'chart_counts_json': json.dumps(chart_counts),
        'pm_chart_labels_json': json.dumps(pm_chart_labels),
        'pm_chart_values_json': json.dumps(pm_chart_values),
        'dt_chart_labels_json': json.dumps(dt_chart_labels),
        'dt_chart_values_json': json.dumps(dt_chart_values),
        # Other
        'delivery_stats': delivery_stats,
        'recent_large': recent_large,
    }

    return render(request, 'sales/dashboard.html', context)


@login_required(login_url='login')
def invoice_list(request):
    """List all sales invoices with filtering and search"""
    today = timezone.now().date()

    # FIXED: Optimized query with select_related and prefetch_related
    # PHASE 3: Filter out soft-deleted invoices
    invoices = SaleInvoice.objects.filter(is_deleted=False).select_related(
        'client', 'seller', 'delivery_method', 'payment_method', 'delivery'
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

    # Filter by delivery status
    delivery_status_filter = request.GET.get('delivery_status', '')
    if delivery_status_filter:
        if delivery_status_filter == 'magasin':
            invoices = invoices.filter(delivery_method_type='magasin')
        else:
            invoices = invoices.filter(
                delivery__status=delivery_status_filter
            )

    # Filter by seller
    seller_filter = request.GET.get('seller', '')
    if seller_filter:
        invoices = invoices.filter(seller_id=seller_filter)

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

    # FIXED: Exclude soft-deleted, returned, cancelled, exchanged, draft invoices from statistics
    excluded_statuses = ['returned', 'cancelled', 'draft', 'exchanged']
    today_stats = SaleInvoice.objects.filter(
        date=today,
        is_deleted=False
    ).exclude(status__in=excluded_statuses).aggregate(
        today_total=Sum('total_amount'),
        today_count=Count('id')
    )

    month_stats = SaleInvoice.objects.filter(
        date__year=today.year,
        date__month=today.month,
        is_deleted=False
    ).exclude(status__in=excluded_statuses).aggregate(
        month_total=Sum('total_amount'),
        month_count=Count('id')
    )

    total_stats = SaleInvoice.objects.filter(
        is_deleted=False
    ).exclude(status__in=excluded_statuses).aggregate(
        total_invoices=Count('id'),
        total_revenue=Sum('total_amount')
    )

    # Subtract refunds (returns on still-active invoices) from these revenue figures
    def _refunds_for(invoice_date_filter):
        return SaleInvoiceAction.objects.filter(
            action_type=SaleInvoiceAction.ActionType.RETURN,
            original_invoice__is_deleted=False,
            **invoice_date_filter,
        ).exclude(
            original_invoice__status__in=excluded_statuses
        ).aggregate(t=Sum('refund_amount'))['t'] or Decimal('0')

    today_refunds = _refunds_for({'original_invoice__date': today})
    month_refunds = _refunds_for({'original_invoice__date__year': today.year, 'original_invoice__date__month': today.month})
    total_refunds = _refunds_for({})

    stats = {
        'today': (today_stats['today_total'] or Decimal('0')) - today_refunds,
        'today_count': today_stats['today_count'] or 0,
        'month': (month_stats['month_total'] or Decimal('0')) - month_refunds,
        'month_count': month_stats['month_count'] or 0,
        'total_invoices': total_stats['total_invoices'] or 0,
        'total_revenue': (total_stats['total_revenue'] or Decimal('0')) - total_refunds,
    }

    from django.contrib.auth import get_user_model
    User = get_user_model()

    context = {
        'page_obj': page_obj,
        'invoices': page_obj.object_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'seller_filter': seller_filter,
        'delivery_status_filter': delivery_status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'stats': stats,
        'statuses': SaleInvoice.Status.choices,
        'sellers': User.objects.filter(is_active=True).order_by('first_name'),
    }

    return render(request, 'sales/invoice_list.html', context)


def _return_exchange_datetime(request):
    """
    Parse the optional `action_date` from the Return/Exchange modal so the
    operator can record when the return/exchange actually happened (today or a
    past date). Returns (aware_datetime, date). Defaults to now / today; a
    future date is clamped to today.
    """
    from datetime import datetime as _dt, time as _time
    raw = (request.POST.get('action_date') or '').strip()
    today = timezone.localdate()
    try:
        d = _dt.strptime(raw, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        d = today
    now = timezone.now()
    if d >= today:
        return now, today
    aware = timezone.make_aware(_dt.combine(d, _time(12, 0)), timezone.get_current_timezone())
    return aware, d


@login_required(login_url='login')
def invoice_detail(request, reference):
    """Display invoice details"""
    invoice = get_object_or_404(
        SaleInvoice.objects.select_related(
            'client', 'seller', 'delivery_method'
        ).prefetch_related('items', 'items__product'),
        reference=reference,
        is_deleted=False
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
            refund_method = request.POST.get('refund_method', 'cash')
            refund_amount_str = request.POST.get('refund_amount', '')
            deposit_client_id = request.POST.get('deposit_client_id', '')
            action_dt, _action_date = _return_exchange_datetime(request)

            if refund_method not in ('cash', 'deposit', 'none'):
                refund_method = 'cash'

            if item_id:
                try:
                    item = SaleInvoiceItem.objects.get(id=item_id, invoice=invoice)
                    product = item.product
                    product_ref = product.reference

                    # Resolve refund amount (default = full item amount), capped at item total
                    item_total = item.total_amount or Decimal('0')
                    try:
                        refund_amount = Decimal(refund_amount_str) if refund_amount_str != '' else item_total
                    except (InvalidOperation, ValueError):
                        refund_amount = item_total
                    if refund_amount < 0:
                        refund_amount = Decimal('0')
                    if refund_amount > item_total:
                        refund_amount = item_total

                    # For deposit credit, resolve the client to credit
                    deposit_client = None
                    if refund_method == 'deposit':
                        from clients.models import Client
                        deposit_client = Client.objects.filter(pk=deposit_client_id).first() if deposit_client_id else None
                        if not deposit_client:
                            messages.error(request, 'Veuillez sélectionner un client pour le crédit dépôt.')
                            return redirect('sales:invoice_detail', reference=reference)

                    # Mark item as returned
                    item.is_returned = True
                    item.returned_at = action_dt
                    item.save(update_fields=['is_returned', 'returned_at'])

                    # Create action record (stores refund method/amount/deposit client)
                    _return_action = SaleInvoiceAction.objects.create(
                        original_invoice=invoice,
                        action_type=SaleInvoiceAction.ActionType.RETURN,
                        original_product=product,
                        original_product_ref=product_ref,
                        refund_amount=refund_amount,
                        refund_method=refund_method,
                        deposit_client=deposit_client,
                        notes=notes,
                        created_by=request.user
                    )
                    # Record it on the chosen return date (today or backdated).
                    SaleInvoiceAction.objects.filter(pk=_return_action.pk).update(created_at=action_dt)

                    # If crediting a client deposit, create the deposit transaction
                    if refund_method == 'deposit' and deposit_client and refund_amount > 0:
                        from deposits.models import DepositAccount, DepositTransaction
                        dep_account, _ = DepositAccount.objects.get_or_create(
                            client=deposit_client,
                            defaults={'created_by': request.user}
                        )
                        _dep_tx = DepositTransaction.objects.create(
                            account=dep_account,
                            transaction_type=DepositTransaction.TransactionType.REFUND,
                            amount=refund_amount,  # positive: credit into deposit
                            description=f'Remboursement retour facture {invoice.reference} ({product_ref})',
                            created_by=request.user
                        )
                        DepositTransaction.objects.filter(pk=_dep_tx.pk).update(created_at=action_dt)

                    # Update product status to available
                    product.status = 'available'
                    product.save(update_fields=['status'])

                    # Check if ALL items are now returned
                    total_items = invoice.items.count()
                    returned_items = invoice.items.filter(is_returned=True).count()

                    # Total refunded across all return actions on this invoice
                    total_refunded = invoice.actions.filter(
                        action_type=SaleInvoiceAction.ActionType.RETURN
                    ).aggregate(t=Sum('refund_amount'))['t'] or Decimal('0')

                    if returned_items >= total_items and total_refunded >= (invoice.total_amount or Decimal('0')):
                        # All items returned AND fully refunded -> mark invoice as returned
                        invoice.status = SaleInvoice.Status.RETURNED
                        invoice.save(update_fields=['status'])
                        messages.success(request, f'Produit {product_ref} retourné. Tous les articles retournés et remboursés - facture marquée comme retournée.')
                    else:
                        # Partial return or partial refund - keep invoice active (refund is subtracted in stats)
                        remaining_items = total_items - returned_items
                        method_label = {'cash': 'espèce', 'deposit': 'crédit dépôt', 'none': 'sans remboursement'}.get(refund_method, refund_method)
                        messages.success(request, f'Produit {product_ref} retourné. Remboursé: {refund_amount} DH ({method_label}).')
                        if remaining_items > 0:
                            messages.info(request, f'Il reste {remaining_items} article(s) non retourné(s) dans cette facture.')

                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'Returned product {product_ref} from invoice {invoice.reference} (refund {refund_amount} {refund_method})',
                        ip_address=get_client_ip(request)
                    )

                except SaleInvoiceItem.DoesNotExist:
                    messages.error(request, 'Article non trouvé.')

        # Handle creating new invoice from remaining (non-returned) items
        elif action == 'create_from_remaining':
            new_reference = request.POST.get('new_reference', '').strip()

            # Get non-returned items
            remaining_items = invoice.items.filter(is_returned=False)

            if not remaining_items.exists():
                messages.error(request, 'Aucun article non retourné à transférer.')
            else:
                # Validate new reference
                if not new_reference:
                    new_reference = generate_invoice_reference()
                elif SaleInvoice.objects.filter(reference=new_reference, is_deleted=False).exists():
                    messages.error(request, f'La référence "{new_reference}" existe déjà.')
                    return redirect('sales:invoice_detail', reference=reference)

                # Calculate totals for remaining items
                new_subtotal = sum(item.total_amount for item in remaining_items)
                new_discount = sum(item.discount_amount for item in remaining_items)

                # Create new invoice with same client and seller
                new_invoice = SaleInvoice.objects.create(
                    reference=new_reference,
                    date=timezone.now().date(),
                    client=invoice.client,
                    seller=request.user,
                    status=SaleInvoice.Status.PAID,  # Assume already paid from original
                    subtotal=new_subtotal,
                    discount_amount=new_discount,
                    total_amount=new_subtotal,
                    amount_paid=new_subtotal,  # Already paid
                    balance_due=Decimal('0'),
                    notes=f'Créée à partir de la facture {invoice.reference} (articles restants après retour)'
                )

                # Move remaining items to new invoice
                for item in remaining_items:
                    # Create new item in new invoice
                    SaleInvoiceItem.objects.create(
                        invoice=new_invoice,
                        product=item.product,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        original_price=item.original_price,
                        negotiated_price=item.negotiated_price,
                        discount_amount=item.discount_amount,
                        total_amount=item.total_amount,
                        notes=f'Transféré depuis {invoice.reference}'
                    )
                    # Mark original item as transferred (using is_returned)
                    item.is_returned = True
                    item.returned_at = timezone.now()
                    item.notes = f'Transféré vers {new_reference}'
                    item.save()

                # Mark original invoice as returned (all items now handled)
                invoice.status = SaleInvoice.Status.RETURNED
                invoice.save(update_fields=['status'])

                # Log activity
                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.CREATE,
                    model_name='SaleInvoice',
                    object_id=str(new_invoice.id),
                    object_repr=f'Created {new_reference} from remaining items of {invoice.reference}',
                    ip_address=get_client_ip(request)
                )

                messages.success(request, f'Nouvelle facture {new_reference} créée avec les {remaining_items.count()} article(s) restant(s).')
                return redirect('sales:invoice_detail', reference=new_reference)

        # Handle exchange action (supports multiple products and payment)
        elif action == 'exchange_item':
            import json

            item_id = request.POST.get('item_id')
            replacement_products_json = request.POST.get('replacement_products', '[]')
            new_invoice_reference = request.POST.get('new_invoice_reference', '').strip()
            action_dt, action_date = _return_exchange_datetime(request)
            # Payment 1
            payment_method_id = request.POST.get('payment_method_id', '')
            payment_reference = request.POST.get('payment_reference', '').strip()
            bank_account_id = request.POST.get('bank_account_id', '')
            amount_paid_str = request.POST.get('amount_paid', '0')
            # Payment 2 (hybrid)
            payment_method_id_2 = request.POST.get('payment_method_id_2', '')
            payment_reference_2 = request.POST.get('payment_reference_2', '').strip()
            bank_account_id_2 = request.POST.get('bank_account_id_2', '')
            amount_paid_str_2 = request.POST.get('amount_paid_2', '0')
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
                        if SaleInvoice.objects.filter(reference=new_invoice_reference, is_deleted=False).exists():
                            messages.error(request, f'La référence "{new_invoice_reference}" existe déjà. Veuillez en choisir une autre.')
                            return redirect('sales:invoice_detail', reference=reference)
                        exchange_reference = new_invoice_reference
                    else:
                        exchange_reference = generate_invoice_reference()

                    # Create new invoice for the exchange
                    new_invoice = SaleInvoice.objects.create(
                        reference=exchange_reference,
                        date=action_date,
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

                    # First, copy all OTHER items from original invoice (not the exchanged one)
                    other_items_total = Decimal('0')
                    for other_item in invoice.items.exclude(id=item_id):
                        SaleInvoiceItem.objects.create(
                            invoice=new_invoice,
                            product=other_item.product,
                            quantity=other_item.quantity,
                            original_price=other_item.original_price,
                            negotiated_price=other_item.negotiated_price,
                            unit_price=other_item.unit_price,
                            total_amount=other_item.total_amount,
                        )
                        other_items_total += other_item.total_amount
                        # Note: These products keep their current status (already sold)

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

                    # Handle hybrid payments
                    # The logic:
                    # - Original invoice was already paid (amount_paid on original invoice)
                    # - We transfer that payment to the new invoice
                    # - The DIFFERENCE to pay is: new_invoice.total - original_invoice.total
                    # - Plus any additional payment(s) the client makes now
                    from payments.models import ClientPayment

                    # Parse payment amounts
                    try:
                        amount_paid_1 = Decimal(amount_paid_str)
                    except (InvalidOperation, ValueError):
                        amount_paid_1 = Decimal('0')

                    try:
                        amount_paid_2 = Decimal(amount_paid_str_2)
                    except (InvalidOperation, ValueError):
                        amount_paid_2 = Decimal('0')

                    amount_paid_input = amount_paid_1 + amount_paid_2
                    payment_details = []

                    # Create ClientPayment records for each payment (works for both clients and anonymous sales)
                    if amount_paid_1 > 0 and payment_method_id:
                        try:
                            pm1 = PaymentMethod.objects.get(id=payment_method_id)
                            payment_details.append({'method': pm1.name, 'amount': amount_paid_1})

                            pay_ref_1 = payment_reference if payment_reference else f"PAY-{new_invoice.reference}-1"
                            ClientPayment.objects.create(
                                reference=pay_ref_1,
                                date=action_date,
                                payment_type=ClientPayment.PaymentType.INVOICE,
                                client=new_invoice.client,  # Can be None for anonymous sales
                                amount=amount_paid_1,
                                payment_method=pm1,
                                bank_account_id=bank_account_id or None,
                                sale_invoice=new_invoice,
                                created_by=request.user
                            )
                        except PaymentMethod.DoesNotExist:
                            pass
                        except ValueError as e:
                            messages.error(request, str(e))
                            return redirect('sales:invoice_detail', reference=reference)

                    if amount_paid_2 > 0 and payment_method_id_2:
                        try:
                            pm2 = PaymentMethod.objects.get(id=payment_method_id_2)
                            payment_details.append({'method': pm2.name, 'amount': amount_paid_2})

                            pay_ref_2 = payment_reference_2 if payment_reference_2 else f"PAY-{new_invoice.reference}-2"
                            ClientPayment.objects.create(
                                reference=pay_ref_2,
                                date=action_date,
                                payment_type=ClientPayment.PaymentType.INVOICE,
                                client=new_invoice.client,  # Can be None for anonymous sales
                                amount=amount_paid_2,
                                payment_method=pm2,
                                bank_account_id=bank_account_id_2 or None,
                                sale_invoice=new_invoice,
                                created_by=request.user
                            )
                        except PaymentMethod.DoesNotExist:
                            pass
                        except ValueError as e:
                            messages.error(request, str(e))
                            return redirect('sales:invoice_detail', reference=reference)

                    # Calculate the difference to pay
                    # Old invoice total was already paid, so transfer that amount
                    original_invoice_total = invoice.total_amount  # Total of original invoice (all items)
                    original_amount_paid = invoice.amount_paid  # What was already paid on original

                    # Difference = new total - old total (can be positive or negative)
                    difference = new_invoice.total_amount - original_invoice_total

                    # Total payment = what was paid before + what client pays now
                    total_payment = original_amount_paid + amount_paid_input

                    if total_payment >= new_invoice.total_amount:
                        # Fully paid
                        new_invoice.amount_paid = new_invoice.total_amount
                        new_invoice.balance_due = Decimal('0')
                        new_invoice.status = SaleInvoice.Status.PAID
                    elif total_payment > 0:
                        # Partial payment
                        new_invoice.amount_paid = total_payment
                        new_invoice.balance_due = new_invoice.total_amount - total_payment
                        new_invoice.status = SaleInvoice.Status.PARTIAL_PAID
                    else:
                        # Nothing paid
                        new_invoice.amount_paid = Decimal('0')
                        new_invoice.balance_due = new_invoice.total_amount
                        new_invoice.status = SaleInvoice.Status.UNPAID

                    new_invoice.save()

                    # Create action record (link to first replacement product for reference)
                    _exchange_action = SaleInvoiceAction.objects.create(
                        original_invoice=invoice,
                        action_type=SaleInvoiceAction.ActionType.EXCHANGE,
                        original_product=original_product,
                        original_product_ref=original_ref,
                        new_invoice=new_invoice,
                        replacement_product=first_replacement,
                        notes=notes,
                        created_by=request.user
                    )
                    # Record it on the chosen exchange date (today or backdated).
                    SaleInvoiceAction.objects.filter(pk=_exchange_action.pk).update(created_at=action_dt)

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
    ).select_related('category', 'metal_type', 'metal_purity').order_by('-created_at')

    # Get action history
    invoice_actions = invoice.actions.select_related(
        'original_product', 'replacement_product', 'new_invoice', 'created_by'
    ).all()

    # Get payment methods and bank accounts for exchange modal
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)

    # Get all payments associated with this invoice
    invoice_payments = invoice.payments.select_related('payment_method', 'bank_account').all()

    # Exchange credit (reprise) applied TO this invoice — this is how it was "paid"
    # when the customer traded in items instead of paying cash.
    exchange_credits = list(
        invoice.exchange_from.filter(action_type='exchange')
        .select_related('original_invoice', 'original_product')
    )
    exchange_credit_total = sum((a.refund_amount or Decimal('0')) for a in exchange_credits)
    # Surplus handed back to the customer when the trade-in exceeded the invoice total
    exchange_surplus = exchange_credit_total - invoice.total_amount
    if exchange_surplus < 0:
        exchange_surplus = Decimal('0')

    # Get remaining (non-returned) items for partial return handling
    all_items = list(invoice.items.select_related('product__metal_type').all())
    # Compute per-item prix/g and invoice-level total weight + prix/g
    invoice_total_weight = Decimal('0')
    for item in all_items:
        w = item.product.gross_weight or Decimal('0')
        item.prix_per_gram = (item.total_amount / w) if w > 0 else Decimal('0')
        if not item.is_returned:
            invoice_total_weight += w
    invoice_prix_per_gram = (invoice.total_amount / invoice_total_weight) if invoice_total_weight > 0 else Decimal('0')
    remaining_items = invoice.items.filter(is_returned=False)
    returned_items_count = invoice.items.filter(is_returned=True).count()
    has_remaining_items = remaining_items.exists() and returned_items_count > 0
    remaining_items_total = sum(item.total_amount for item in remaining_items) if has_remaining_items else 0

    context = {
        'invoice': invoice,
        'items': all_items,
        'invoice_total_weight': invoice_total_weight,
        'invoice_prix_per_gram': invoice_prix_per_gram,
        'products': products,
        'exchange_products': exchange_products,
        'invoice_actions': invoice_actions,
        'payment_methods': payment_methods,
        'bank_accounts': bank_accounts,
        'invoice_payments': invoice_payments,
        'exchange_credits': exchange_credits,
        'exchange_credit_total': exchange_credit_total,
        'exchange_surplus': exchange_surplus,
        'remaining_items': remaining_items if has_remaining_items else [],
        'remaining_items_count': remaining_items.count() if has_remaining_items else 0,
        'remaining_items_total': remaining_items_total,
        'has_remaining_items': has_remaining_items,
    }

    return render(request, 'sales/invoice_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def add_invoice_item(request, reference):
    """Add an item to an existing invoice"""
    try:
        # Get the invoice
        invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False)

        # Staff can add items to any invoice, others only draft
        if invoice.status != 'draft' and not request.user.is_staff:
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

        # Staff can delete items from any invoice, others only draft
        if invoice.status != 'draft' and not request.user.is_staff:
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
@require_http_methods(["POST"])
def add_invoice_photo(request, reference):
    """Attach one or more sale photos (Photos de Vente) to an invoice."""
    try:
        invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False)
        if not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

        from .models import InvoicePhoto
        from products.views import convert_image_to_jpeg

        files = request.FILES.getlist('photos')
        if not files and 'photo' in request.FILES:
            files = [request.FILES['photo']]
        if not files:
            return JsonResponse({'success': False, 'error': 'Aucune image fournie'}, status=400)

        valid_types = dict(InvoicePhoto.PhotoType.choices)
        ptype = request.POST.get('photo_type', 'other')
        if ptype not in valid_types:
            ptype = 'other'

        created = []
        for f in files:
            img = convert_image_to_jpeg(f)
            p = InvoicePhoto.objects.create(invoice=invoice, image=img, photo_type=ptype)
            created.append({
                'id': p.id,
                'url': request.build_absolute_uri(p.image.url),
                'type': p.get_photo_type_display(),
            })

        ActivityLog.objects.create(
            user=request.user, action=ActivityLog.ActionType.UPDATE,
            model_name='SaleInvoice', object_id=str(invoice.id),
            object_repr=f'{invoice.reference} (+{len(created)} photo)',
            ip_address=get_client_ip(request))

        return JsonResponse({'success': True, 'photos': created})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception('add_invoice_photo failed')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='login')
@require_http_methods(["POST"])
def delete_invoice_photo(request, photo_id):
    """Delete a sale photo from an invoice."""
    try:
        from .models import InvoicePhoto
        photo = get_object_or_404(InvoicePhoto, id=photo_id)
        if not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)
        ref = photo.invoice.reference
        photo.delete()
        ActivityLog.objects.create(
            user=request.user, action=ActivityLog.ActionType.UPDATE,
            model_name='SaleInvoice', object_id=str(photo.invoice_id),
            object_repr=f'{ref} (-1 photo)', ip_address=get_client_ip(request))
        return JsonResponse({'success': True})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception('delete_invoice_photo failed')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='login')
@require_http_methods(["POST"])
def update_invoice_item(request):
    """Update price/quantity of an existing invoice item (AJAX)"""
    import json
    try:
        item_id = request.POST.get('item_id')
        if not item_id:
            return JsonResponse({'success': False, 'error': 'ID article requis'}, status=400)

        item = get_object_or_404(SaleInvoiceItem, id=item_id)
        invoice = item.invoice

        # Staff can edit any invoice
        if not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission refusee'}, status=403)

        # Update negotiated price
        new_price = request.POST.get('negotiated_price')
        if new_price is not None and new_price != '':
            try:
                new_price = Decimal(new_price)
                if new_price < 0:
                    return JsonResponse({'success': False, 'error': 'Le prix ne peut pas etre negatif'}, status=400)
                item.negotiated_price = new_price
                item.unit_price = new_price
                item.total_amount = new_price * item.quantity
            except (InvalidOperation, TypeError):
                return JsonResponse({'success': False, 'error': 'Prix invalide'}, status=400)

        # Update quantity
        new_qty = request.POST.get('quantity')
        if new_qty is not None and new_qty != '':
            try:
                new_qty = Decimal(new_qty)
                if new_qty <= 0:
                    return JsonResponse({'success': False, 'error': 'Quantite invalide'}, status=400)
                item.quantity = new_qty
                price = item.negotiated_price or item.unit_price
                item.total_amount = price * new_qty
            except (InvalidOperation, TypeError):
                return JsonResponse({'success': False, 'error': 'Quantite invalide'}, status=400)

        item.save()

        # Recalculate invoice totals
        invoice.calculate_totals()
        invoice.save()

        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.UPDATE,
            model_name='SaleInvoiceItem',
            object_id=str(item.id),
            object_repr=f"{invoice.reference} - {item.product.name}",
            ip_address=get_client_ip(request)
        )

        return JsonResponse({
            'success': True,
            'message': 'Article mis a jour',
            'item_total': str(item.total_amount),
            'invoice_subtotal': str(invoice.subtotal),
            'invoice_discount': str(invoice.discount_amount),
            'invoice_total': str(invoice.total_amount),
        })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Error updating invoice item: {str(e)}')
        return JsonResponse({'success': False, 'error': 'Erreur serveur'}, status=500)


@login_required(login_url='login')
@require_http_methods(["POST"])
def update_payment(request):
    """Update an existing ClientPayment (AJAX) - staff only"""
    from payments.models import ClientPayment
    try:
        if not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission refusee'}, status=403)

        payment_id = request.POST.get('payment_id')
        if not payment_id:
            return JsonResponse({'success': False, 'error': 'ID paiement requis'}, status=400)

        payment = get_object_or_404(ClientPayment, id=payment_id)
        invoice = payment.sale_invoice

        # Update amount
        new_amount = request.POST.get('amount')
        if new_amount is not None and new_amount != '':
            try:
                new_amount = Decimal(new_amount)
                if new_amount <= 0:
                    return JsonResponse({'success': False, 'error': 'Montant invalide'}, status=400)
                old_amount = payment.amount
                payment.amount = new_amount
            except (InvalidOperation, TypeError):
                return JsonResponse({'success': False, 'error': 'Montant invalide'}, status=400)

        # Update payment method
        new_pm_id = request.POST.get('payment_method_id')
        if new_pm_id:
            payment.payment_method_id = int(new_pm_id)

        # Update bank account
        new_ba_id = request.POST.get('bank_account_id')
        if new_ba_id == '':
            payment.bank_account = None
        elif new_ba_id:
            payment.bank_account_id = int(new_ba_id)

        # Update reference
        new_ref = request.POST.get('reference')
        if new_ref is not None:
            payment.reference = new_ref or f"PAY-{payment.id}"

        payment.save()

        # Recalculate invoice payment totals
        if invoice:
            total_paid = ClientPayment.objects.filter(
                sale_invoice=invoice
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            invoice.amount_paid = total_paid
            invoice.balance_due = invoice.total_amount - total_paid
            if total_paid >= invoice.total_amount:
                invoice.status = 'paid'
            elif total_paid > 0:
                invoice.status = 'partial'
            else:
                invoice.status = 'unpaid'
            invoice.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement mis a jour',
            'amount_paid': str(invoice.amount_paid) if invoice else '0',
            'balance_due': str(invoice.balance_due) if invoice else '0',
            'status': invoice.status if invoice else '',
        })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Error updating payment: {str(e)}')
        return JsonResponse({'success': False, 'error': 'Erreur serveur'}, status=500)


@login_required(login_url='login')
@require_http_methods(["POST"])
def delete_payment(request):
    """Delete a ClientPayment (AJAX) - staff only"""
    from payments.models import ClientPayment
    try:
        if not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission refusee'}, status=403)

        payment_id = request.POST.get('payment_id')
        if not payment_id:
            return JsonResponse({'success': False, 'error': 'ID paiement requis'}, status=400)

        payment = get_object_or_404(ClientPayment, id=payment_id)
        invoice = payment.sale_invoice
        payment_repr = f"{payment.reference} - {payment.amount} DH"

        payment.delete()

        # Recalculate invoice payment totals
        if invoice:
            total_paid = ClientPayment.objects.filter(
                sale_invoice=invoice
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            invoice.amount_paid = total_paid
            invoice.balance_due = invoice.total_amount - total_paid
            if total_paid >= invoice.total_amount:
                invoice.status = 'paid'
            elif total_paid > 0:
                invoice.status = 'partial'
            else:
                invoice.status = 'unpaid'
            invoice.save()

        ActivityLog.objects.create(
            user=request.user,
            action=ActivityLog.ActionType.DELETE,
            model_name='ClientPayment',
            object_id=payment_id,
            object_repr=payment_repr,
            ip_address=get_client_ip(request)
        )

        return JsonResponse({
            'success': True,
            'message': 'Paiement supprime',
            'amount_paid': str(invoice.amount_paid) if invoice else '0',
            'balance_due': str(invoice.balance_due) if invoice else '0',
            'status': invoice.status if invoice else '',
        })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Error deleting payment: {str(e)}')
        return JsonResponse({'success': False, 'error': 'Erreur serveur'}, status=500)


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
                    if SaleInvoice.objects.filter(reference=custom_reference, is_deleted=False).exists():
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

                # Handle payments (multiple payment lines support)
                from payments.models import ClientPayment

                total_amount_paid = Decimal('0')
                payment_details = []

                # Process multiple payment lines
                import logging
                logger = logging.getLogger(__name__)

                for key in request.POST:
                    if key.startswith('payments[') and key.endswith(']'):
                        try:
                            payment_json = request.POST.get(key)
                            logger.info(f"Processing payment key={key}, json={payment_json}")
                            payment_data = json.loads(payment_json)
                            payment_amount = Decimal(str(payment_data.get('amount', 0)))
                            method_id = payment_data.get('method_id')

                            logger.info(f"Payment data: amount={payment_amount}, method_id={method_id}")

                            if payment_amount > 0 and method_id:
                                total_amount_paid += payment_amount

                                # Get payment method
                                payment_method = PaymentMethod.objects.get(id=method_id)

                                # Create ClientPayment record (works for both clients and anonymous sales)
                                payment_ref = payment_data.get('reference', '').strip()
                                if not payment_ref:
                                    # Auto-generate reference if not provided
                                    payment_ref = f"PAY-{invoice.reference}-{len(payment_details)+1}"

                                ClientPayment.objects.create(
                                    reference=payment_ref,
                                    date=timezone.now().date(),
                                    payment_type=ClientPayment.PaymentType.INVOICE,
                                    client=invoice.client,  # Can be None for anonymous sales
                                    amount=payment_amount,
                                    payment_method=payment_method,
                                    bank_account_id=payment_data.get('bank_account_id') or None,
                                    sale_invoice=invoice,
                                    created_by=request.user
                                )

                                payment_details.append({
                                    'method': payment_method.name,
                                    'amount': payment_amount
                                })

                        except (json.JSONDecodeError, PaymentMethod.DoesNotExist) as e:
                            print(f'Error processing payment: {e}')
                            continue
                        except ValueError as e:
                            messages.error(request, str(e))
                            return redirect('sales:invoice_create')

                # Fallback: Check for simple amount_paid field (backward compatibility)
                if total_amount_paid == 0:
                    try:
                        amount_paid = Decimal(str(request.POST.get('amount_paid', '0')))
                        if amount_paid > 0:
                            total_amount_paid = amount_paid
                    except (InvalidOperation, ValueError):
                        pass

                if total_amount_paid > 0:
                    # SET the amount_paid (capped at total — any trade-in surplus is
                    # handed back to the customer, not owed to the shop)
                    invoice.amount_paid = min(total_amount_paid, invoice.total_amount)
                    invoice.balance_due = invoice.total_amount - invoice.amount_paid
                    invoice.update_status()
                    invoice.save(update_fields=['amount_paid', 'balance_due', 'status'])

                    # UPDATE PRODUCT STATUS: If invoice is now PAID, mark product as sold
                    if invoice.status == SaleInvoice.Status.PAID:
                        for item in invoice.items.all():
                            item.product.status = 'sold'
                            item.product.save(update_fields=['status'])
                    # Note: if status is UNPAID or PARTIAL, product stays 'indisponible' (reserved)

                    # Log the payment activity
                    payment_summary = ', '.join([f"{p['method']}: {p['amount']} DH" for p in payment_details]) if payment_details else f"{total_amount_paid} DH"
                    ActivityLog.objects.create(
                        user=request.user,
                        action=ActivityLog.ActionType.UPDATE,
                        model_name='SaleInvoice',
                        object_id=str(invoice.id),
                        object_repr=f'{invoice.reference} - Paiements: {payment_summary}',
                        ip_address=get_client_ip(request)
                    )

                amount_paid = total_amount_paid  # For message generation below

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

                # Send Telegram notification to admin
                try:
                    from telegram_bot.notifications import notify_admin_new_sale
                    notify_admin_new_sale(invoice)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Telegram notification error: {e}")

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
        'payment_methods': PaymentMethod.objects.filter(is_active=True),
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
            # Get transaction date (default to today)
            from datetime import datetime
            transaction_date_str = request.POST.get('transaction_date', '')
            if transaction_date_str:
                transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
            else:
                transaction_date = timezone.now().date()

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
            # Second payment (hybrid)
            payment_methods_2 = request.POST.getlist('payment_method_2')
            payment_references_2 = request.POST.getlist('payment_reference_2')
            amount_paids_2 = request.POST.getlist('amount_paid_2')
            bank_accounts_2 = request.POST.getlist('bank_account_2')

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
                    if SaleInvoice.objects.filter(reference=custom_ref, is_deleted=False).exists():
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

                    # Create invoice with custom transaction date
                    invoice = SaleInvoice.objects.create(
                        reference=reference,
                        date=transaction_date,
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
                    # Support for hybrid payments (payment 1 + payment 2)
                    from payments.models import ClientPayment

                    total_amount_paid = Decimal('0')
                    payment_details = []

                    # Payment 1
                    if i < len(amount_paids) and amount_paids[i].strip():
                        try:
                            amount_paid_1 = Decimal(amount_paids[i])
                            if amount_paid_1 > 0:
                                total_amount_paid += amount_paid_1
                                payment_method_id = payment_methods[i] if i < len(payment_methods) else ''
                                if payment_method_id:
                                    try:
                                        pm = PaymentMethod.objects.get(id=payment_method_id)
                                        payment_details.append({'method': pm.name, 'amount': amount_paid_1})

                                        # Create ClientPayment record (works for both clients and anonymous sales)
                                        pay_ref = payment_references[i].strip() if i < len(payment_references) else ''
                                        if not pay_ref:
                                            pay_ref = f"PAY-{invoice.reference}-1"
                                        ClientPayment.objects.create(
                                            reference=pay_ref,
                                            date=transaction_date,
                                            payment_type=ClientPayment.PaymentType.INVOICE,
                                            client=client,  # Can be None for anonymous sales
                                            amount=amount_paid_1,
                                            payment_method=pm,
                                            bank_account_id=bank_accounts[i] if i < len(bank_accounts) and bank_accounts[i] else None,
                                            sale_invoice=invoice,
                                            created_by=request.user
                                        )
                                    except PaymentMethod.DoesNotExist:
                                        pass
                                    except ValueError as e:
                                        messages.error(request, f'Ligne {i+1}: {e}')
                        except (InvalidOperation, ValueError):
                            pass

                    # Payment 2 (hybrid)
                    if i < len(amount_paids_2) and amount_paids_2[i].strip():
                        try:
                            amount_paid_2 = Decimal(amount_paids_2[i])
                            if amount_paid_2 > 0:
                                total_amount_paid += amount_paid_2
                                payment_method_id_2 = payment_methods_2[i] if i < len(payment_methods_2) else ''
                                if payment_method_id_2:
                                    try:
                                        pm2 = PaymentMethod.objects.get(id=payment_method_id_2)
                                        payment_details.append({'method': pm2.name, 'amount': amount_paid_2})

                                        # Create ClientPayment record (works for both clients and anonymous sales)
                                        pay_ref_2 = payment_references_2[i].strip() if i < len(payment_references_2) else ''
                                        if not pay_ref_2:
                                            pay_ref_2 = f"PAY-{invoice.reference}-2"
                                        ClientPayment.objects.create(
                                            reference=pay_ref_2,
                                            date=transaction_date,
                                            payment_type=ClientPayment.PaymentType.INVOICE,
                                            client=client,  # Can be None for anonymous sales
                                            amount=amount_paid_2,
                                            payment_method=pm2,
                                            bank_account_id=bank_accounts_2[i] if i < len(bank_accounts_2) and bank_accounts_2[i] else None,
                                            sale_invoice=invoice,
                                            created_by=request.user
                                        )
                                    except PaymentMethod.DoesNotExist:
                                        pass
                                    except ValueError as e:
                                        messages.error(request, f'Ligne {i+1}: {e}')
                        except (InvalidOperation, ValueError):
                            pass

                    # Update invoice with total payments
                    if total_amount_paid > 0:
                        # Cap at total — trade-in surplus is handed back, not owed to the shop
                        invoice.amount_paid = min(total_amount_paid, invoice.total_amount)

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
                        payment_summary = ', '.join([f"{p['method']}: {p['amount']} DH" for p in payment_details]) if payment_details else f"{total_amount_paid} DH"
                        ActivityLog.objects.create(
                            user=request.user,
                            action=ActivityLog.ActionType.CREATE,
                            model_name='Payment',
                            object_id=str(invoice.id),
                            object_repr=f'Paiements: {payment_summary} - {invoice.reference}',
                            ip_address=get_client_ip(request)
                        )

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

                    # Send Telegram notification to admin
                    try:
                        from telegram_bot.notifications import notify_admin_new_sale
                        notify_admin_new_sale(invoice)
                    except Exception as notif_err:
                        logger.error(f"Telegram notification error for {invoice.reference}: {notif_err}")

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
        'today': timezone.now().date(),
    }

    return render(request, 'sales/bulk_invoice_form.html', context)


@login_required(login_url='login')
def invoice_detail_view(request, reference):
    """Display detailed invoice with payment options"""
    invoice = get_object_or_404(
        SaleInvoice.objects.select_related(
            'client', 'seller', 'delivery_method'
        ).prefetch_related('items'),
        reference=reference,
        is_deleted=False
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
def payment_list(request):
    """List all payment records with search, filters, and stats"""
    from payments.models import ClientPayment
    from settings_app.models import PaymentMethod

    payments = ClientPayment.objects.select_related(
        'client', 'sale_invoice', 'payment_method', 'bank_account', 'created_by'
    ).order_by('-date', '-created_at')

    # Search by reference, client name, or invoice reference
    search_query = request.GET.get('search', '')
    if search_query:
        payments = payments.filter(
            Q(reference__icontains=search_query) |
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query) |
            Q(sale_invoice__reference__icontains=search_query)
        )

    # Filter by payment type
    type_filter = request.GET.get('type', '')
    if type_filter:
        payments = payments.filter(payment_type=type_filter)

    # Filter by payment method
    method_filter = request.GET.get('method', '')
    if method_filter:
        payments = payments.filter(payment_method_id=method_filter)

    # Filter by date range
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        payments = payments.filter(date__gte=date_from)
    if date_to:
        payments = payments.filter(date__lte=date_to)

    # Stats on filtered queryset
    today = timezone.now().date()
    stats = {
        'total_count': payments.count(),
        'total_amount': payments.aggregate(t=Sum('amount'))['t'] or Decimal('0'),
        'today_count': payments.filter(date=today).count(),
        'today_amount': payments.filter(date=today).aggregate(t=Sum('amount'))['t'] or Decimal('0'),
    }

    # Pagination
    paginator = Paginator(payments, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'payments': page_obj.object_list,
        'search_query': search_query,
        'type_filter': type_filter,
        'method_filter': method_filter,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'payment_types': ClientPayment.PaymentType.choices,
        'payment_methods': PaymentMethod.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'sales/payment_list.html', context)


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
    """Edit existing invoice - staff can edit any invoice"""
    from .forms import SaleInvoiceForm
    from settings_app.models import Carrier

    invoice = get_object_or_404(
        SaleInvoice.objects.select_related('client', 'seller', 'carrier', 'payment_method', 'bank_account'),
        reference=reference,
        is_deleted=False
    )

    # Check permissions - staff can edit any, others only their own drafts
    if not request.user.is_staff:
        if invoice.status != SaleInvoice.Status.DRAFT:
            messages.error(request, 'Seuls les brouillons peuvent être édités.')
            return redirect('sales:invoice_detail', reference=reference)
        if request.user != invoice.created_by:
            messages.error(request, 'Vous n\'avez pas la permission d\'éditer cette facture.')
            return redirect('sales:invoice_detail', reference=reference)

    items = invoice.items.select_related('product').order_by('id')
    form = None

    if request.method == 'POST':
        try:
            form = SaleInvoiceForm(request.POST, instance=invoice)
            if form.is_valid():
                inv = form.save(commit=False)
                inv.save()
                inv.calculate_totals()
                inv.save()

                # Keep the linked delivery in sync with the edited invoice, so a
                # changed tracking number / method / carrier is reflected on the
                # Livraisons page and in the AMANA reconciliation.
                from .models import Delivery
                try:
                    delivery = inv.delivery
                except Delivery.DoesNotExist:
                    delivery = None
                if delivery:
                    delivery.tracking_number = inv.tracking_number or ''
                    delivery.delivery_method_type = inv.delivery_method_type
                    delivery.carrier = inv.carrier
                    delivery.total_amount = inv.total_amount
                    if inv.client:
                        delivery.client_name = inv.client.full_name
                        delivery.client_phone = inv.client.phone
                    delivery.save()

                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='SaleInvoice',
                    object_id=str(invoice.id),
                    object_repr=invoice.reference,
                    ip_address=get_client_ip(request)
                )

                messages.success(request, 'Facture mise à jour avec succès.')
                return redirect('sales:invoice_detail', reference=inv.reference)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        field_label = form.fields[field].label if field in form.fields else field
                        messages.error(request, f'{field_label}: {error}')
        except Exception as e:
            messages.error(request, f'Erreur lors de la mise à jour: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error editing invoice {reference}: {str(e)}')

    if form is None:
        form = SaleInvoiceForm(instance=invoice)

    from django.contrib.auth import get_user_model
    from payments.models import ClientPayment
    from settings_app.models import PaymentMethod, BankAccount
    User = get_user_model()

    # Get payments linked to this invoice
    invoice_payments = ClientPayment.objects.filter(
        sale_invoice=invoice
    ).select_related('payment_method', 'bank_account').order_by('date', 'id')

    context = {
        'invoice': invoice,
        'form': form,
        'items': items,
        'invoice_payments': invoice_payments,
        'payment_methods': PaymentMethod.objects.filter(is_active=True).order_by('display_order', 'name'),
        'bank_accounts': BankAccount.objects.filter(is_active=True).order_by('bank_name'),
        'sellers': User.objects.filter(is_active=True).order_by('first_name'),
        'carriers': Carrier.objects.filter(is_active=True).order_by('name'),
        'clients': Client.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        'products': Product.objects.filter(status='available').select_related('category').order_by('reference'),
    }

    return render(request, 'sales/invoice_edit.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_delete(request, reference):
    """Delete (soft delete) invoice - staff can delete any invoice"""
    invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False)

    # Check permissions - staff can delete any, others only their own drafts
    if not request.user.is_staff:
        if invoice.status != SaleInvoice.Status.DRAFT:
            messages.error(request, 'Seules les factures brouillons peuvent être supprimées.')
            return redirect('sales:invoice_detail', reference=reference)
        if request.user != invoice.created_by:
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
    """Record payment for invoice - supports dual/hybrid payments with custom date"""
    from django.db import transaction
    from django.utils import timezone
    from datetime import timedelta, datetime
    from decimal import Decimal
    from payments.models import ClientPayment

    invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False)

    # Check permissions
    if not request.user.is_staff:
        messages.error(request, 'Vous n\'avez pas la permission d\'enregistrer un paiement.')
        return redirect('sales:invoice_detail', reference=reference)

    if request.method == 'POST':
        try:
            notes = request.POST.get('notes', '').strip()

            # Collect any number of payment rows (indices 1..N)
            payment_rows = []
            for idx in range(1, 51):
                method_id = request.POST.get(f'payment_method_{idx}', '')
                try:
                    amount = Decimal(request.POST.get(f'amount_{idx}', '0') or '0')
                except (InvalidOperation, ValueError):
                    amount = Decimal('0')
                if amount > 0 and method_id:
                    date_str = request.POST.get(f'payment_date_{idx}', '')
                    try:
                        pay_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
                    except ValueError:
                        pay_date = timezone.now().date()
                    payment_rows.append({
                        'index': idx,
                        'amount': amount,
                        'method_id': method_id,
                        'ref': request.POST.get(f'payment_reference_{idx}', '').strip(),
                        'bank_id': request.POST.get(f'bank_account_{idx}', ''),
                        'date': pay_date,
                        'dep_client_id': request.POST.get(f'deposit_client_id_{idx}', ''),
                    })

            total_payment = sum((r['amount'] for r in payment_rows), Decimal('0'))

            if total_payment <= 0:
                messages.error(request, 'Le montant du paiement doit être supérieur à 0.')
                return redirect('sales:invoice_payment', reference=reference)

            # SECURITY: Use transaction lock to prevent race conditions
            with transaction.atomic():
                # Re-fetch with lock to get current state
                invoice = SaleInvoice.objects.select_for_update().get(id=invoice.id)

                # Validate amount doesn't exceed balance (re-check after lock)
                if total_payment > invoice.balance_due:
                    messages.error(
                        request,
                        f'Le paiement ne peut pas dépasser le solde dû ({invoice.balance_due} DH)'
                    )
                    return redirect('sales:invoice_payment', reference=reference)

                # SECURITY: Check for duplicate payment (same amount within 10 seconds)
                recent_payments = ActivityLog.objects.filter(
                    user=request.user,
                    action=ActivityLog.ActionType.CREATE,
                    model_name='ClientPayment',
                    created_at__gte=timezone.now() - timedelta(seconds=10),
                    object_repr__icontains=invoice.reference
                ).count()

                if recent_payments > 0:
                    messages.error(
                        request,
                        'Un paiement a été enregistré récemment. Veuillez patienter.'
                    )
                    return redirect('sales:invoice_payment', reference=reference)

                # Helper: deduct from client deposit if payment method is "Dépôt Client"
                def handle_deposit_deduction(pm, amount, pay_date, dep_client_id=''):
                    if pm.name.lower() in ('dépôt client', 'depot client', 'dépôt'):
                        from deposits.models import DepositAccount, DepositTransaction
                        from clients.models import Client as ClientModel
                        try:
                            # Use the selected deposit client, or fallback to invoice client
                            dep_client = None
                            if dep_client_id:
                                try:
                                    dep_client = ClientModel.objects.get(pk=int(dep_client_id))
                                except (ClientModel.DoesNotExist, ValueError):
                                    dep_client = None

                            if not dep_client and invoice.client:
                                dep_client = invoice.client

                            if not dep_client:
                                messages.warning(
                                    request,
                                    'Aucun client sélectionné pour le dépôt. Le paiement a été enregistré sans déduction.'
                                )
                                return

                            dep_account = dep_client.deposit_account
                            if dep_account.balance >= amount:
                                DepositTransaction.objects.create(
                                    account=dep_account,
                                    transaction_type=DepositTransaction.TransactionType.PURCHASE,
                                    amount=-amount,
                                    invoice=invoice,
                                    description=f"Paiement facture {invoice.reference} (dépôt {dep_client.full_name})",
                                    date=pay_date,
                                    created_by=request.user,
                                )
                            else:
                                messages.warning(
                                    request,
                                    f'Solde dépôt insuffisant pour {dep_client.full_name} ({dep_account.balance} DH). '
                                    f'Le paiement a été enregistré mais le dépôt n\'a pas été déduit.'
                                )
                        except DepositAccount.DoesNotExist:
                            messages.warning(
                                request,
                                f'{dep_client.full_name if dep_client else "Ce client"} n\'a pas de compte dépôt. '
                                f'Le paiement a été enregistré sans déduction.'
                            )

                # Create all payment rows
                for n, row in enumerate(payment_rows, start=1):
                    pm = PaymentMethod.objects.get(id=row['method_id'])
                    ClientPayment.objects.create(
                        # Use the typed reference, else leave blank so the model
                        # auto-generates a unique one (avoids PAY-<inv>-N collisions
                        # when adding payments across multiple sessions).
                        reference=row['ref'] or '',
                        date=row['date'],
                        payment_type=ClientPayment.PaymentType.INVOICE,
                        client=invoice.client,
                        amount=row['amount'],
                        payment_method=pm,
                        bank_account_id=row['bank_id'] if row['bank_id'] else None,
                        sale_invoice=invoice,
                        notes=notes,
                        created_by=request.user
                    )

                    # Deduct from deposit if applicable
                    handle_deposit_deduction(pm, row['amount'], row['date'], row['dep_client_id'])

                    # Use the first payment's method as the invoice's primary method
                    if n == 1:
                        invoice.payment_method = pm
                        if row['ref']:
                            invoice.payment_reference = row['ref']
                        if row['bank_id']:
                            invoice.bank_account_id = row['bank_id']

                # Recalculate invoice payment totals from actual DB records
                # (ClientPayment.save() already incremented amount_paid via update_payment(),
                #  so we recalculate from source of truth to avoid double-counting)
                invoice.refresh_from_db()
                actual_paid = ClientPayment.objects.filter(
                    sale_invoice=invoice
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

                invoice.amount_paid = actual_paid
                invoice.balance_due = invoice.total_amount - actual_paid

                if actual_paid >= invoice.total_amount:
                    invoice.status = SaleInvoice.Status.PAID
                elif actual_paid > 0:
                    invoice.status = SaleInvoice.Status.PARTIAL_PAID
                else:
                    invoice.status = SaleInvoice.Status.UNPAID

                invoice.save()

                # Log activity
                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.CREATE,
                    model_name='ClientPayment',
                    object_id=str(invoice.id),
                    object_repr=f'{invoice.reference} - Paiement {total_payment} DH',
                    ip_address=get_client_ip(request)
                )

                messages.success(request, f'Paiement de {total_payment} DH enregistré.')
                return redirect('sales:invoice_detail', reference=reference)

        except Exception as e:
            messages.error(request, f'Erreur lors de l\'enregistrement du paiement: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f'Error recording payment for {reference}: {str(e)}')

    # GET request - show form
    # Get client deposit balance if client exists
    deposit_balance = Decimal('0')
    if invoice.client:
        try:
            deposit_account = invoice.client.deposit_account
            deposit_balance = deposit_account.balance
        except Exception:
            deposit_balance = Decimal('0')

    context = {
        'invoice': invoice,
        'remaining': invoice.balance_due,
        'today': timezone.now().date(),
        'payment_methods': PaymentMethod.objects.filter(is_active=True).order_by('display_order', 'name'),
        'bank_accounts': BankAccount.objects.filter(is_active=True),
        'deposit_balance': deposit_balance,
    }

    return render(request, 'sales/invoice_payment.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def invoice_delivery(request, reference):
    """Update delivery information"""
    from .forms import DeliveryForm

    invoice = get_object_or_404(SaleInvoice, reference=reference, is_deleted=False)

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
    from settings_app.models import ProductCategory, MetalType, MetalPurity, Carrier

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

            # Save custom reference if provided (preserve it across add_item actions)
            custom_reference = request.POST.get('custom_reference', '').strip()
            if custom_reference and custom_reference != invoice.reference:
                if not SaleInvoice.objects.filter(reference=custom_reference, is_deleted=False).exclude(id=invoice.id).exists():
                    invoice.reference = custom_reference
                    invoice.save(update_fields=['reference'])

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

            # Save custom reference if provided (preserve it across remove_item actions)
            custom_reference = request.POST.get('custom_reference', '').strip()
            if custom_reference and custom_reference != invoice.reference:
                if not SaleInvoice.objects.filter(reference=custom_reference, is_deleted=False).exclude(id=invoice.id).exists():
                    invoice.reference = custom_reference
                    invoice.save(update_fields=['reference'])

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
                # Keep the invoice's original date (set when the draft was
                # created via Telegram) instead of stamping today. Completing
                # an old pending sale must not change its invoice date.
                # (Payment dates are recorded separately, per-payment.)
                if not invoice.date:
                    invoice.date = invoice.created_at.date() if invoice.created_at else timezone.now().date()

                # Handle custom reference update
                custom_reference = request.POST.get('custom_reference', '').strip()
                if custom_reference and custom_reference != invoice.reference:
                    # Check if new reference already exists (among active invoices only)
                    if SaleInvoice.objects.filter(reference=custom_reference, is_deleted=False).exclude(id=invoice.id).exists():
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

                # Handle exchange (reprise facture) — supports multiple invoices,
                # each with partial item selection.
                import json as _json
                exchange_credit = Decimal('0')
                # Each entry: {'invoice': SaleInvoice, 'selected': [{item_id, reprise_value}], 'credit': Decimal}
                exchange_entries = []
                _ex_status = [SaleInvoice.Status.PAID, SaleInvoice.Status.PARTIAL_PAID, SaleInvoice.Status.UNPAID]

                def _load_exchange_invoice(inv_id):
                    try:
                        return SaleInvoice.objects.prefetch_related('items__product').get(
                            id=int(inv_id), is_deleted=False, status__in=_ex_status
                        )
                    except (SaleInvoice.DoesNotExist, ValueError, TypeError):
                        return None

                data_json = request.POST.get('exchange_data_json', '')
                if data_json:
                    # New multi-invoice format: [{invoice_id, items:[{item_id, reprise_value}]}]
                    try:
                        parsed = _json.loads(data_json)
                    except _json.JSONDecodeError:
                        parsed = []
                    for entry in parsed:
                        inv = _load_exchange_invoice(entry.get('invoice_id'))
                        if not inv:
                            continue
                        valid_ids = set(inv.items.values_list('id', flat=True))
                        selected = []
                        for si in entry.get('items', []):
                            try:
                                if int(si['item_id']) in valid_ids:
                                    selected.append({'item_id': int(si['item_id']),
                                                     'reprise_value': Decimal(str(si['reprise_value']))})
                            except (KeyError, ValueError, TypeError):
                                continue
                        if not selected:
                            continue
                        credit = sum((si['reprise_value'] for si in selected), Decimal('0'))
                        exchange_credit += credit
                        exchange_entries.append({'invoice': inv, 'selected': selected, 'credit': credit})
                else:
                    # Backward compatibility: old single-invoice fields
                    exchange_invoice_id = request.POST.get('exchange_invoice_id', '')
                    if exchange_invoice_id:
                        inv = _load_exchange_invoice(exchange_invoice_id)
                        if inv:
                            valid_ids = set(inv.items.values_list('id', flat=True))
                            selected = []
                            items_json = request.POST.get('exchange_items_json', '')
                            if items_json:
                                try:
                                    for si in _json.loads(items_json):
                                        if int(si['item_id']) in valid_ids:
                                            selected.append({'item_id': int(si['item_id']),
                                                             'reprise_value': Decimal(str(si['reprise_value']))})
                                except (ValueError, KeyError, TypeError, _json.JSONDecodeError):
                                    selected = []
                            # No explicit item selection -> do NOT default to the
                            # whole invoice (that silently exchanged every item).
                            # Only record an entry when specific items were chosen.
                            if selected:
                                credit = sum((si['reprise_value'] for si in selected), Decimal('0'))
                                exchange_credit += credit
                                exchange_entries.append({'invoice': inv, 'selected': selected, 'credit': credit})

                # Handle dynamic payments (N payments)
                from payments.models import ClientPayment
                from datetime import datetime

                # This invoice is still a DRAFT (guaranteed above). Any ClientPayment
                # already attached to it comes from an earlier failed completion
                # attempt, so clear them before rebuilding the payment set from the
                # form. This makes re-validation idempotent and avoids duplicate rows
                # and PAY-<ref>-<idx> reference collisions on retry. amount_paid is
                # recomputed from the form total further below.
                ClientPayment.objects.filter(sale_invoice=invoice).delete()

                total_amount_paid = exchange_credit
                payment_details = []
                for _entry in exchange_entries:
                    payment_details.append({
                        'method': f"Échange ({_entry['invoice'].reference})",
                        'amount': _entry['credit'],
                    })

                # Find all payment sections by scanning POST keys
                # Payment fields are named: payment_method_1, payment_method_2, etc.
                payment_indices = set()
                for key in request.POST:
                    if key.startswith('payment_method_'):
                        try:
                            idx = int(key.split('_')[-1])
                            payment_indices.add(idx)
                        except (ValueError, IndexError):
                            pass

                # Process each payment
                for idx in sorted(payment_indices):
                    amount_str = request.POST.get(f'amount_paid_{idx}', '0')
                    method_id = request.POST.get(f'payment_method_{idx}', '')
                    pay_ref = request.POST.get(f'payment_reference_{idx}', '').strip()
                    bank_id = request.POST.get(f'bank_account_{idx}', '')
                    date_str = request.POST.get(f'payment_date_{idx}', '')

                    # Parse date
                    if date_str:
                        try:
                            pay_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        except ValueError:
                            pay_date = timezone.now().date()
                    else:
                        pay_date = timezone.now().date()

                    # Parse amount
                    try:
                        amount = Decimal(amount_str)
                    except (InvalidOperation, TypeError):
                        amount = Decimal('0')

                    if amount > 0 and method_id:
                        total_amount_paid += amount
                        try:
                            pm = PaymentMethod.objects.get(id=method_id)
                            payment_details.append({'method': pm.name, 'amount': amount})

                            # Leave the reference blank when the user didn't type one
                            # so the model auto-generates a globally-unique PAY-*.
                            # A deterministic PAY-<ref>-<idx> collides on re-completion.
                            ClientPayment.objects.create(
                                reference=pay_ref or '',
                                date=pay_date,
                                payment_type=ClientPayment.PaymentType.INVOICE,
                                client=invoice.client,
                                amount=amount,
                                payment_method=pm,
                                bank_account_id=bank_id or None,
                                sale_invoice=invoice,
                                created_by=request.user
                            )

                            # Deduct from deposit if payment method is "Dépôt Client"
                            if pm.name.lower() in ('dépôt client', 'depot client', 'dépôt'):
                                from deposits.models import DepositAccount, DepositTransaction
                                dep_client_id = request.POST.get(f'deposit_client_id_{idx}', '')
                                dep_client = None
                                if dep_client_id:
                                    try:
                                        dep_client = Client.objects.get(pk=int(dep_client_id))
                                    except (Client.DoesNotExist, ValueError):
                                        dep_client = None
                                if not dep_client and invoice.client:
                                    dep_client = invoice.client
                                if dep_client:
                                    try:
                                        dep_account = dep_client.deposit_account
                                        if dep_account.balance >= amount:
                                            DepositTransaction.objects.create(
                                                account=dep_account,
                                                transaction_type=DepositTransaction.TransactionType.PURCHASE,
                                                amount=-amount,
                                                invoice=invoice,
                                                description=f"Paiement facture {invoice.reference} (dépôt {dep_client.full_name})",
                                                date=pay_date,
                                                created_by=request.user,
                                            )
                                        else:
                                            messages.warning(
                                                request,
                                                f'Solde dépôt insuffisant pour {dep_client.full_name} ({dep_account.balance} DH).'
                                            )
                                    except DepositAccount.DoesNotExist:
                                        messages.warning(request, f'{dep_client.full_name} n\'a pas de compte dépôt.')

                        except PaymentMethod.DoesNotExist:
                            pass
                        except ValueError as e:
                            messages.error(request, str(e))
                            return redirect('sales:pending_invoice_complete', reference=reference)

                # Set payment amounts and determine status based on total amount paid.
                # Record amount_paid capped at the invoice total: if a trade-in (reprise)
                # is worth more than the new item, the surplus is handed back to the
                # customer (cash/virement), so it must NOT inflate the invoice — otherwise
                # "Total payé" would exceed "Total".
                recorded_paid = min(total_amount_paid, invoice.total_amount)
                invoice.amount_paid = recorded_paid
                invoice.balance_due = invoice.total_amount - recorded_paid

                if total_amount_paid >= invoice.total_amount:
                    invoice.status = SaleInvoice.Status.PAID
                    invoice.balance_due = Decimal('0')  # Ensure no negative balance
                elif total_amount_paid > 0:
                    invoice.status = SaleInvoice.Status.PARTIAL_PAID
                else:
                    invoice.status = SaleInvoice.Status.UNPAID

                # Handle delivery method
                delivery_method_type = request.POST.get('delivery_method_type_hidden', 'magasin')
                invoice.delivery_method_type = delivery_method_type

                tracking_number = request.POST.get('tracking_number_hidden', '').strip()
                invoice.tracking_number = tracking_number

                # Set carrier if transporteur
                carrier_id = request.POST.get('carrier_id_hidden', '')
                if carrier_id and delivery_method_type == 'transporteur':
                    try:
                        from settings_app.models import Carrier
                        invoice.carrier = Carrier.objects.get(id=carrier_id)
                    except Carrier.DoesNotExist:
                        pass

                invoice.save()

                # Create Delivery object for non-magasin deliveries
                if delivery_method_type in ['amana', 'transporteur']:
                    from sales.models import Delivery
                    # Create delivery record
                    Delivery.objects.create(
                        invoice=invoice,
                        client_name=invoice.client.full_name if invoice.client else '',
                        client_phone=invoice.client.phone if invoice.client else '',
                        total_amount=invoice.total_amount,
                        delivery_method_type=delivery_method_type,
                        carrier=invoice.carrier,
                        tracking_number=tracking_number,
                        status='pending'
                    )

                # Create stock storage records for en_stock deliveries
                if delivery_method_type == 'en_stock' and invoice.client:
                    from stock_storage.models import StockStorageAccount, StockStorageItem
                    storage_account, _ = StockStorageAccount.objects.get_or_create(
                        client=invoice.client,
                        defaults={'created_by': request.user}
                    )
                    for inv_item in invoice.items.select_related('product'):
                        if inv_item.product:
                            StockStorageItem.objects.create(
                                account=storage_account,
                                invoice=invoice,
                                product=inv_item.product,
                                product_reference=inv_item.product.reference,
                                product_name=inv_item.product.name,
                                product_weight=inv_item.product.gross_weight or 0,
                                price=inv_item.total_amount or 0,
                                created_by=request.user,
                            )

                # Mark all products in the invoice as sold
                for item in invoice.items.all():
                    if item.product:
                        item.product.status = 'sold'
                        item.product.save(update_fields=['status'])

                # Finalize exchange: for each exchanged invoice, mark ONLY the
                # selected items as returned and return their products.
                if exchange_entries:
                    from sales.models import SaleInvoiceAction
                    for _entry in exchange_entries:
                        ex_inv = _entry['invoice']
                        selected_item_ids = {si['item_id'] for si in _entry['selected']}
                        reprise_values = {si['item_id']: si['reprise_value'] for si in _entry['selected']}

                        for ex_item in ex_inv.items.all():
                            if ex_item.id not in selected_item_ids:
                                continue
                            ex_item.is_returned = True
                            ex_item.returned_at = timezone.now()
                            ex_item.save(update_fields=['is_returned', 'returned_at'])
                            if ex_item.product:
                                ex_item.product.status = 'available'
                                ex_item.product.save(update_fields=['status'])
                            # Per-item action record
                            SaleInvoiceAction.objects.create(
                                original_invoice=ex_inv,
                                action_type=SaleInvoiceAction.ActionType.EXCHANGE,
                                original_product=ex_item.product,
                                original_product_ref=ex_item.product.reference if ex_item.product else '',
                                new_invoice=invoice,
                                refund_amount=reprise_values.get(ex_item.id, ex_item.total_amount),
                                created_by=request.user,
                            )

                        # Mark the old invoice EXCHANGED only if ALL its items are now returned
                        all_returned = not ex_inv.items.filter(is_returned=False).exists()
                        if all_returned:
                            ex_inv.status = SaleInvoice.Status.EXCHANGED
                            ex_inv.save(update_fields=['status'])

                # Log activity
                payment_summary = ', '.join([f"{p['method']}: {p['amount']} DH" for p in payment_details]) if payment_details else 'Aucun paiement'
                ActivityLog.objects.create(
                    user=request.user,
                    action=ActivityLog.ActionType.UPDATE,
                    model_name='SaleInvoice',
                    object_id=str(invoice.id),
                    object_repr=str(invoice),
                    details={'action': 'completed_draft', 'reference': invoice.reference, 'payments': payment_summary}
                )

                messages.success(request, f"Facture {invoice.reference} validée avec succès!")

                # Send Telegram notification to admin
                try:
                    from telegram_bot.notifications import notify_admin_new_sale
                    notify_admin_new_sale(invoice)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Telegram notification error: {e}")

                return redirect('sales:invoice_detail', reference=invoice.reference)

        elif action == 'quick_create_product':
            # Quick product creation
            return _handle_quick_product_creation(request, invoice)

        # Use invoice.reference (not the URL parameter) in case it was updated
        return redirect('sales:pending_invoice_complete', reference=invoice.reference)

    # GET request - show completion form
    # Refresh invoice from database to get latest totals
    invoice.refresh_from_db()

    # Get IDs of products already in the invoice
    products_in_invoice = invoice.items.values_list('product_id', flat=True)

    # Get available products for selection (exclude those already in invoice)
    available_products = Product.objects.filter(
        status='available'
    ).exclude(
        id__in=products_in_invoice
    ).select_related('category', 'metal_type', 'purity').order_by('-created_at')[:100]

    # Get form options
    categories = ProductCategory.objects.filter(is_active=True)
    metals = MetalType.objects.filter(is_active=True)
    purities = MetalPurity.objects.filter(is_active=True)
    clients = Client.objects.filter(is_active=True).order_by('first_name')
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    bank_accounts = BankAccount.objects.filter(is_active=True)
    carriers = Carrier.objects.filter(is_active=True)

    # Get eligible invoices for exchange (non-draft, non-cancelled, non-returned, non-exchanged)
    # Exclude current invoice and invoices where all items are already returned
    exchange_invoices = SaleInvoice.objects.filter(
        is_deleted=False,
        status__in=[SaleInvoice.Status.PAID, SaleInvoice.Status.PARTIAL_PAID, SaleInvoice.Status.UNPAID],
        items__is_returned=False,  # has at least one non-returned item
    ).exclude(
        pk=invoice.pk,
    ).select_related('client').prefetch_related('items__product').distinct().order_by('-date')

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
        'carriers': carriers,
        'exchange_invoices': exchange_invoices,
    }

    return render(request, 'sales/pending_invoice_complete.html', context)


def _handle_quick_product_creation(request, invoice):
    """Handle quick product creation from pending invoice form"""
    from settings_app.models import ProductCategory, MetalType, MetalPurity
    from products.models import Product as ProductModel

    # Preserve custom reference if provided
    custom_reference = request.POST.get('custom_reference', '').strip()
    if custom_reference and custom_reference != invoice.reference:
        if not SaleInvoice.objects.filter(reference=custom_reference, is_deleted=False).exclude(id=invoice.id).exists():
            invoice.reference = custom_reference
            invoice.save(update_fields=['reference'])

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
        # Use margin_type='fixed' with margin_value=selling_price so the save() calculation works
        product = ProductModel.objects.create(
            reference=reference,
            name=f"{category.name} - Création rapide",
            category=category,
            metal_type=metal_type,
            metal_purity=metal_purity,
            gross_weight=weight_decimal,
            net_weight=weight_decimal,
            margin_type='fixed',
            margin_value=selling_price,  # This will be added to total_cost (which is 0) = selling_price
            status='available',
            ai_image_status='skipped',
        )

        # Update selling_price directly in case save() calculation differs
        ProductModel.objects.filter(pk=product.pk).update(selling_price=selling_price)
        product.refresh_from_db()

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
        invoice_id = request.GET.get('invoice_id', '')

        if len(query) < 2:
            return JsonResponse({'products': []})

        # Search only AVAILABLE products (disponible)
        products = Product.objects.filter(
            status='available'
        ).filter(
            Q(reference__icontains=query) |
            Q(name__icontains=query) |
            Q(category__name__icontains=query)
        )

        # Exclude products already in the invoice
        if invoice_id:
            try:
                invoice = SaleInvoice.objects.get(id=invoice_id)
                products_in_invoice = invoice.items.values_list('product_id', flat=True)
                products = products.exclude(id__in=products_in_invoice)
            except SaleInvoice.DoesNotExist:
                pass

        products = products.select_related('category', 'metal_type', 'metal_purity').order_by('-created_at')[:limit]

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


@login_required(login_url='login')
@require_http_methods(["POST"])
def quick_create_client(request):
    """AJAX endpoint to quickly create a client with first name, last name, phone"""
    import json
    import re

    try:
        data = json.loads(request.body)
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        phone = data.get('phone', '').strip()

        if not first_name or not last_name or not phone:
            return JsonResponse({'success': False, 'error': 'Prénom, Nom et Téléphone sont requis.'})

        # Normalize phone: remove spaces, dashes, dots, parentheses
        phone_clean = re.sub(r'[\s\-\.\(\)]+', '', phone)

        # Check if client with same phone already exists (try both raw and cleaned)
        existing = Client.objects.filter(
            Q(phone=phone) | Q(phone=phone_clean)
        ).first()

        # Also check by stripping all non-digit chars for broader match
        if not existing:
            phone_digits = re.sub(r'\D', '', phone)
            if len(phone_digits) >= 8:
                for client in Client.objects.all().only('id', 'phone', 'first_name', 'last_name'):
                    client_digits = re.sub(r'\D', '', client.phone)
                    if client_digits == phone_digits:
                        existing = client
                        break

        if existing:
            return JsonResponse({
                'success': True,
                'id': existing.id,
                'full_name': existing.full_name,
                'phone': existing.phone,
                'existing': True,
                'message': f'Client existant: {existing.full_name} ({existing.phone})'
            })

        client = Client.objects.create(
            first_name=first_name,
            last_name=last_name,
            phone=phone_clean,
            is_active=True
        )

        return JsonResponse({
            'success': True,
            'id': client.id,
            'full_name': client.full_name,
            'phone': client.phone,
            'existing': False
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# =============================================================================
# LIVRAISONS (DELIVERY TRACKING) VIEWS
# =============================================================================

@login_required(login_url='login')
def delivery_list(request):
    """List all deliveries (non-magasin) with status tracking"""
    from .models import Delivery

    deliveries = Delivery.objects.select_related(
        'invoice', 'invoice__seller', 'carrier', 'repair'
    ).prefetch_related('timeline').order_by('-created_at')

    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        deliveries = deliveries.filter(
            Q(reference__icontains=search_query) |
            Q(tracking_number__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(invoice__reference__icontains=search_query)
        )

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        deliveries = deliveries.filter(status=status_filter)

    # Filter by delivery method type
    method_filter = request.GET.get('method', '')
    if method_filter:
        deliveries = deliveries.filter(delivery_method_type=method_filter)

    # Filter by seller (of the linked invoice)
    seller_filter = request.GET.get('seller', '')
    if seller_filter:
        deliveries = deliveries.filter(invoice__seller_id=seller_filter)

    # Filter by payment state: 'cod' = à encaisser (has carrier-collected payment),
    # 'paid' = déjà payée en caisse (no carrier-collected payment)
    from payments.models import ClientPayment as _CP
    paid_filter = request.GET.get('paid', '')
    if paid_filter in ('cod', 'paid'):
        cod_invoice_ids = _CP.objects.filter(
            payment_method__collected_by_carrier=True
        ).values_list('sale_invoice_id', flat=True)
        if paid_filter == 'cod':
            deliveries = deliveries.filter(invoice_id__in=cod_invoice_ids)
        else:
            deliveries = deliveries.exclude(invoice_id__in=cod_invoice_ids)

    # Stats
    stats = {
        'total': Delivery.objects.count(),
        'pending': Delivery.objects.filter(status='pending').count(),
        'in_transit': Delivery.objects.filter(status='in_transit').count(),
        'delivered': Delivery.objects.filter(status='delivered').count(),
    }

    # Total left to collect (COD) = payments via carrier-collection methods on
    # not-yet-delivered deliveries in the filtered set.
    from payments.models import ClientPayment
    cod_to_collect = ClientPayment.objects.filter(
        sale_invoice__delivery__in=deliveries.exclude(status='delivered'),
        payment_method__collected_by_carrier=True,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # Sellers for the filter dropdown
    from django.contrib.auth import get_user_model
    User = get_user_model()
    sellers = User.objects.filter(sales__isnull=False).distinct().order_by('first_name', 'last_name')

    # Pagination
    paginator = Paginator(deliveries, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Per-delivery COD amount (sum of carrier-collected payments on its invoice)
    page_invoice_ids = [d.invoice_id for d in page_obj if d.invoice_id]
    cod_rows = ClientPayment.objects.filter(
        sale_invoice_id__in=page_invoice_ids,
        payment_method__collected_by_carrier=True,
    ).values('sale_invoice_id').annotate(t=Sum('amount'))
    cod_by_invoice = {r['sale_invoice_id']: r['t'] for r in cod_rows}
    for d in page_obj:
        d.cod_amount = cod_by_invoice.get(d.invoice_id, Decimal('0'))

    context = {
        'deliveries': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'method_filter': method_filter,
        'seller_filter': seller_filter,
        'paid_filter': paid_filter,
        'sellers': sellers,
        'cod_to_collect': cod_to_collect,
    }

    return render(request, 'sales/delivery_list.html', context)


@login_required(login_url='login')
def delivery_detail(request, reference):
    """View delivery details and timeline"""
    from .models import Delivery

    delivery = get_object_or_404(
        Delivery.objects.select_related('invoice', 'invoice__seller', 'carrier', 'repair').prefetch_related('timeline'),
        reference=reference
    )

    # COD = amount to be collected by the carrier (payments via carrier-collection methods)
    cod_amount = Decimal('0')
    if delivery.invoice_id:
        from payments.models import ClientPayment
        cod_amount = ClientPayment.objects.filter(
            sale_invoice_id=delivery.invoice_id,
            payment_method__collected_by_carrier=True,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    context = {
        'delivery': delivery,
        'timeline': delivery.timeline.all().order_by('-event_number'),
        'cod_amount': cod_amount,
        'cod_collected': delivery.status == 'delivered',
    }

    return render(request, 'sales/delivery_detail.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def delivery_update_status(request, reference):
    """Manually update delivery status (AJAX) - staff only"""
    from .models import Delivery, DeliveryTimelineEvent

    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission refusee'}, status=403)

    delivery = get_object_or_404(Delivery, reference=reference)
    new_status = request.POST.get('status')

    valid_statuses = ['pending', 'in_transit', 'to_pickup', 'delivered', 'returned']
    if new_status not in valid_statuses:
        return JsonResponse({'success': False, 'error': 'Statut invalide'}, status=400)

    old_status = delivery.status
    delivery.status = new_status

    # Set delivery date if marking as delivered
    if new_status == 'delivered' and not delivery.delivery_date:
        delivery.delivery_date = timezone.now().strftime('%d/%m/%Y')

    delivery.save()

    # Add timeline event
    DeliveryTimelineEvent.objects.create(
        delivery=delivery,
        event_number='M',
        event_date=timezone.now().strftime('%d/%m/%Y'),
        event_time=timezone.now().strftime('%H:%M'),
        description=f'Statut changé manuellement: {old_status} → {new_status}',
        location='',
        source='manual',
    )

    # Update linked invoice delivery_status
    if delivery.invoice:
        invoice = delivery.invoice
        if new_status == 'delivered':
            invoice.delivery_status = 'delivered'
            invoice.delivery_date = timezone.now().date()
        elif new_status == 'returned':
            invoice.delivery_status = 'pending'
        elif new_status == 'in_transit':
            invoice.delivery_status = 'in_transit'
        elif new_status == 'pending':
            invoice.delivery_status = 'pending'
        invoice.save(update_fields=['delivery_status', 'delivery_date'] if new_status == 'delivered' else ['delivery_status'])

    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.UPDATE,
        model_name='Delivery',
        object_id=str(delivery.id),
        object_repr=f'{delivery.reference}: {old_status} → {new_status}',
        ip_address=get_client_ip(request),
    )

    status_labels = {
        'pending': 'En attente',
        'in_transit': 'En transit',
        'to_pickup': 'À récupérer',
        'delivered': 'Livré',
        'returned': 'Retourné',
    }

    return JsonResponse({
        'success': True,
        'message': f'Statut mis à jour: {status_labels.get(new_status, new_status)}',
        'new_status': new_status,
        'new_status_label': status_labels.get(new_status, new_status),
    })


@login_required(login_url='login')
def delivery_check(request, reference):
    """Manually trigger AMANA tracking check for a delivery"""
    from .models import Delivery
    from .services import AmanaTracker

    delivery = get_object_or_404(Delivery, reference=reference)

    if delivery.delivery_method_type != 'amana' or not delivery.tracking_number:
        messages.warning(request, "Cette livraison n'a pas de numéro de suivi AMANA.")
        return redirect('sales:delivery_detail', reference=reference)

    tracker = AmanaTracker()
    try:
        success = tracker.update_delivery(delivery)
        if success:
            messages.success(request, f"Statut mis à jour: {delivery.get_status_display()}")
        else:
            messages.warning(request, "Impossible de récupérer les informations de suivi.")
    except Exception as e:
        messages.error(request, "Erreur de connexion au service AMANA. Le service est temporairement indisponible.")

    return redirect('sales:delivery_detail', reference=reference)


@login_required(login_url='login')
def delivery_bulk_check(request):
    """
    Returns a page that performs bulk check via client-side JavaScript.
    Server-side requests to Cloudflare timeout from German server,
    so we use client-side fetching instead.
    """
    from django.conf import settings
    from .models import Delivery

    # Get all AMANA deliveries that are not delivered or returned
    deliveries = Delivery.objects.filter(
        delivery_method_type='amana',
        tracking_number__isnull=False
    ).exclude(
        tracking_number=''
    ).exclude(
        status__in=['delivered', 'returned']
    )

    proxy_url = getattr(settings, 'AMANA_PROXY_URL', '')

    return render(request, 'sales/delivery_bulk_check.html', {
        'deliveries': deliveries,
        'proxy_url': proxy_url,
    })


@login_required(login_url='login')
@require_http_methods(["POST"])
def delivery_update_from_client(request, reference):
    """
    API endpoint to receive tracking data fetched from client-side.
    The client's browser fetches from AMANA (using their IP) and sends results here.
    This bypasses geo-blocking since the request comes from the user's location.
    """
    import json
    from .models import Delivery, DeliveryTimelineEvent

    delivery = get_object_or_404(Delivery, reference=reference)

    if delivery.delivery_method_type != 'amana':
        return JsonResponse({'success': False, 'error': 'Not an AMANA delivery'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    if not data.get('success'):
        return JsonResponse({
            'success': False,
            'error': data.get('error', 'Tracking fetch failed')
        })

    # Update delivery fields from client-side data
    delivery.product = data.get('product', '') or ''
    delivery.weight = data.get('weight', '') or ''
    delivery.amount_cod = data.get('amount', '') or ''
    delivery.current_position = data.get('current_position', '') or ''
    delivery.destination = data.get('destination', '') or ''
    delivery.origin = data.get('origin', '') or ''
    delivery.deposit_date = data.get('deposit_date', '') or ''
    delivery.delivery_date = data.get('delivery_date', '') or ''
    delivery.last_checked_at = timezone.now()

    # Update timeline if we have events
    timeline_data = data.get('timeline', [])
    if timeline_data:
        # Delete old timeline events from AMANA
        delivery.timeline.filter(source='amana').delete()

        # Create new timeline events
        for event in timeline_data:
            DeliveryTimelineEvent.objects.create(
                delivery=delivery,
                event_number=event.get('number', ''),
                event_date=event.get('date', ''),
                event_time=event.get('time', ''),
                description=event.get('description', ''),
                location=event.get('location', ''),
                source='amana'
            )

    # Determine status from the last timeline event description
    def detect_status_from_timeline(timeline_data, delivery_date):
        """Detect delivery status based on the last timeline event"""
        if delivery_date:
            return 'delivered'

        if not timeline_data:
            return 'pending'

        # Get the last (most recent) event - it's the first in the list (highest number)
        last_event = timeline_data[0] if timeline_data else None
        if not last_event:
            return 'in_transit'

        description = last_event.get('description', '').lower()

        # Check for "livré" (delivered)
        if 'livré' in description or 'livre' in description:
            return 'delivered'

        # Check for "à récupérer" (to pickup)
        if 'récupérer' in description or 'recuperer' in description:
            return 'to_pickup'

        # Check for "retourné" or "retour" (returned)
        if 'retourné' in description or 'retourne' in description or 'retour à l' in description:
            return 'returned'

        # Default to in_transit
        return 'in_transit'

    delivery.status = detect_status_from_timeline(timeline_data, data.get('delivery_date'))

    delivery.save(update_fields=[
        'status', 'product', 'weight', 'amount_cod',
        'current_position', 'destination', 'origin',
        'deposit_date', 'delivery_date', 'last_checked_at'
    ])

    # Update invoice delivery status if different
    if delivery.invoice:
        status_map = {
            'pending': 'pending',
            'in_transit': 'in_transit',
            'to_pickup': 'in_transit',  # Map to_pickup to in_transit for invoice
            'delivered': 'delivered',
            'returned': 'pending'  # Map returned to pending for invoice
        }
        new_invoice_status = status_map.get(delivery.status, 'pending')
        if delivery.invoice.delivery_status != new_invoice_status:
            delivery.invoice.delivery_status = new_invoice_status
            delivery.invoice.save(update_fields=['delivery_status'])

    return JsonResponse({
        'success': True,
        'status': delivery.status,
        'status_display': delivery.get_status_display(),
        'message': f'Statut mis à jour: {delivery.get_status_display()}'
    })


# ===========================================================================
# Poste Livraison — dedicated workspace for the AMANA delivery responsable
# ===========================================================================

def _delivery_desk_access(view):
    """Allow the delivery responsable, plus managers/admins/staff."""
    from functools import wraps

    @wraps(view)
    @login_required(login_url='login')
    def _wrapped(request, *args, **kwargs):
        u = request.user
        if getattr(u, 'role', None) in ('delivery', 'admin', 'manager') or u.is_staff or u.is_superuser:
            return view(request, *args, **kwargs)
        messages.error(request, "Accès réservé au poste livraison.")
        return redirect('dashboard')
    return _wrapped


def _delivery_log(delivery, request, description):
    """Write a manual timeline event + ActivityLog for a responsable action."""
    from .models import DeliveryTimelineEvent
    DeliveryTimelineEvent.objects.create(
        delivery=delivery, event_number='M',
        event_date=timezone.now().strftime('%d/%m/%Y'),
        event_time=timezone.now().strftime('%H:%M'),
        description=description, location='', source='manual',
    )
    ActivityLog.objects.create(
        user=request.user, action=ActivityLog.ActionType.UPDATE,
        model_name='Delivery', object_id=str(delivery.id),
        object_repr=f'{delivery.reference}: {description}',
        ip_address=get_client_ip(request),
    )


def _cod_by_invoice(deliveries):
    """Map invoice_id -> COD amount (carrier-collected payments) for a set of deliveries."""
    from payments.models import ClientPayment
    inv_ids = [d.invoice_id for d in deliveries if d.invoice_id]
    if not inv_ids:
        return {}
    rows = (ClientPayment.objects.filter(
        sale_invoice_id__in=inv_ids, payment_method__collected_by_carrier=True)
        .values('sale_invoice_id').annotate(t=Sum('amount')))
    return {r['sale_invoice_id']: r['t'] for r in rows}


@_delivery_desk_access
def delivery_desk(request):
    """AMANA delivery responsable board, three tabs: En attente / Tous / Retours."""
    from .models import Delivery

    active_tab = request.GET.get('tab', 'attente')
    if active_tab not in ('attente', 'tous', 'retours'):
        active_tab = 'attente'
    search = (request.GET.get('search') or '').strip()

    base = Delivery.objects.filter(delivery_method_type='amana').select_related(
        'invoice', 'invoice__seller', 'return_received_by')

    def _search(qs):
        if search:
            return qs.filter(
                Q(reference__icontains=search) | Q(tracking_number__icontains=search) |
                Q(client_name__icontains=search) | Q(invoice__reference__icontains=search))
        return qs

    pending = list(_search(base.filter(status='pending')).order_by('-created_at'))
    returns_todo = list(_search(base.filter(status='returned', return_received_at__isnull=True)).order_by('-updated_at'))
    returns_done = list(_search(base.filter(status='returned', return_received_at__isnull=False)).order_by('-return_received_at')[:50])

    all_qs = _search(base).order_by('-created_at')
    paginator = Paginator(all_qs, 40)
    all_page = paginator.get_page(request.GET.get('page', 1))

    cod = _cod_by_invoice(list(pending) + list(all_page))
    for d in pending:
        d.cod_amount = cod.get(d.invoice_id, Decimal('0'))
    for d in all_page:
        d.cod_amount = cod.get(d.invoice_id, Decimal('0'))

    return render(request, 'sales/delivery_desk.html', {
        'active_tab': active_tab,
        'search': search,
        'pending': pending,
        'returns_todo': returns_todo,
        'returns_done': returns_done,
        'all_page': all_page,
        'counts': {
            'attente': len(pending),
            'retours': len(returns_todo),
            'tous': paginator.count,
        },
    })


@_delivery_desk_access
@require_http_methods(["POST"])
def delivery_desk_receive_return(request, reference):
    """Responsable confirms physical reception of a returned parcel from AMANA,
    with a photo of the received return. Logistical acknowledgment only: does
    NOT restock the product or touch the invoice (another operator finalizes)."""
    from .models import Delivery, DeliveryPhoto
    delivery = get_object_or_404(Delivery, reference=reference, delivery_method_type='amana')
    if delivery.status != 'returned':
        return JsonResponse({'ok': False, 'error': "Cette livraison n'est pas un retour."}, status=400)
    if delivery.return_received_at:
        return JsonResponse({'ok': False, 'error': 'Retour déjà réceptionné.'}, status=409)
    photo = request.FILES.get('photo')
    if not photo:
        return JsonResponse({'ok': False, 'error': 'Photo du retour réceptionné requise.'}, status=400)
    delivery.return_received_at = timezone.now()
    delivery.return_received_by = request.user
    delivery.save(update_fields=['return_received_at', 'return_received_by', 'updated_at'])
    DeliveryPhoto.objects.create(
        delivery=delivery, image=photo,
        photo_type=DeliveryPhoto.PhotoType.RETURN_RECEPTION, uploaded_by=request.user)
    _delivery_log(delivery, request, 'Retour réceptionné (physique, photo jointe) par le responsable livraison')
    return JsonResponse({'ok': True})


@_delivery_desk_access
@require_http_methods(["POST"])
def delivery_desk_update_code(request, reference):
    """Responsable changes the AMANA tracking code (recoded at the counter),
    with a photo of the modified sheet."""
    from .models import Delivery, DeliveryPhoto
    delivery = get_object_or_404(Delivery, reference=reference, delivery_method_type='amana')
    new_code = (request.POST.get('tracking_number') or '').strip()
    if not new_code:
        return JsonResponse({'ok': False, 'error': 'Code vide.'}, status=400)
    old_code = delivery.tracking_number or '(vide)'
    if new_code == delivery.tracking_number:
        return JsonResponse({'ok': True, 'unchanged': True, 'tracking_number': new_code})
    photo = request.FILES.get('photo')
    if not photo:
        return JsonResponse({'ok': False, 'error': 'Photo du bordereau modifié requise.'}, status=400)
    delivery.tracking_number = new_code
    delivery.save(update_fields=['tracking_number', 'updated_at'])
    # Keep the invoice's tracking in sync when present.
    if delivery.invoice_id and hasattr(delivery.invoice, 'tracking_number'):
        delivery.invoice.tracking_number = new_code
        try:
            delivery.invoice.save(update_fields=['tracking_number'])
        except Exception:
            pass
    DeliveryPhoto.objects.create(
        delivery=delivery, image=photo,
        photo_type=DeliveryPhoto.PhotoType.CODE_CHANGE,
        note=f'{old_code} → {new_code}', uploaded_by=request.user)
    _delivery_log(delivery, request, f'Code AMANA modifié : {old_code} → {new_code} (photo jointe)')
    return JsonResponse({'ok': True, 'tracking_number': new_code})


@_delivery_desk_access
def delivery_desk_papers(request, reference):
    """Return the Telegram sales papers (invoice photos) attached to the
    delivery's invoice, so the responsable can see the bon de vente."""
    from .models import Delivery
    delivery = get_object_or_404(
        Delivery.objects.select_related('invoice', 'invoice__client'),
        reference=reference, delivery_method_type='amana')
    inv = delivery.invoice
    photos = []
    if inv:
        for p in inv.photos.all():
            try:
                url = p.image.url
            except Exception:
                url = ''
            if url:
                photos.append({
                    'url': url,
                    'type': p.get_photo_type_display(),
                    'caption': p.caption or '',
                })
    client = delivery.client_name or (inv.client.full_name if inv and inv.client_id else '')
    return JsonResponse({
        'ok': True,
        'invoice_ref': inv.reference if inv else '',
        'client': client,
        'photos': photos,
    })


@login_required(login_url='login')
@require_http_methods(["POST"])
def ai_extract_sales_photo(request):
    """Extract data from a sales invoice photo using AI vision."""
    from .models import InvoicePhoto

    try:
        photo_id = request.POST.get('photo_id')
        if not photo_id:
            return JsonResponse({'success': False, 'error': 'Photo ID requis'}, status=400)

        photo = get_object_or_404(InvoicePhoto, id=photo_id)

        # Read the image file
        if not photo.image or not photo.image.path:
            return JsonResponse({'success': False, 'error': 'Photo introuvable'}, status=404)

        from ai_services.sales_ocr import extract_sales_data
        result = extract_sales_data(photo.image.path)

        if 'error' in result:
            return JsonResponse({'success': False, 'error': result['error']}, status=400)

        return JsonResponse({'success': True, 'data': result})

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'AI extract sales error: {str(e)}')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =============================================================================
# DATA EXPORTS (per-section CSV + background full ZIP)
# =============================================================================
import csv as _csv
import io as _io


def _csv_text(header, rows):
    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(header)
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def _x(v):
    """Format a Decimal/number for CSV."""
    try:
        return f"{(v or 0):.2f}"
    except Exception:
        return '0.00'


def _ds_invoices(qs):
    header = ['Référence', 'Date', 'Statut', 'Client', 'Téléphone', 'Type livraison',
              'Total', 'Payé', 'Solde', 'Méthode', 'Vendeur']
    rows = []
    for inv in qs.select_related('client', 'payment_method', 'seller'):
        seller = ''
        if inv.seller:
            seller = inv.seller.get_full_name() or inv.seller.username
        rows.append([
            inv.reference,
            inv.date.strftime('%Y-%m-%d') if inv.date else '',
            inv.get_status_display(),
            inv.client.full_name if inv.client else 'Anonyme',
            inv.client.phone if inv.client else '',
            inv.get_delivery_method_type_display(),
            _x(inv.total_amount), _x(inv.amount_paid), _x(inv.balance_due),
            inv.payment_method.name if inv.payment_method else '',
            seller,
        ])
    return _csv_text(header, rows)


def _ds_payments(qs):
    header = ['Référence', 'Date', 'Facture', 'Client', 'Méthode', 'Banque', 'Montant']
    rows = []
    for p in qs.select_related('sale_invoice', 'sale_invoice__client', 'payment_method', 'bank_account'):
        rows.append([
            p.reference,
            p.date.strftime('%Y-%m-%d') if p.date else '',
            p.sale_invoice.reference if p.sale_invoice else '',
            (p.sale_invoice.client.full_name if p.sale_invoice and p.sale_invoice.client else 'Anonyme'),
            p.payment_method.name if p.payment_method else '',
            p.bank_account.bank_name if p.bank_account else '',
            _x(p.amount),
        ])
    return _csv_text(header, rows)


def _ds_returns(qs):
    header = ['Date', 'Facture', 'Produit', 'Montant remboursé', 'Mode remboursement',
              'Client crédité (dépôt)', 'Notes', 'Par']
    method_map = dict(SaleInvoiceAction.RefundMethod.choices)
    rows = []
    for a in qs.select_related('original_invoice', 'deposit_client', 'created_by'):
        by = ''
        if a.created_by:
            by = a.created_by.get_full_name() or a.created_by.username
        rows.append([
            a.created_at.strftime('%Y-%m-%d %H:%M') if a.created_at else '',
            a.original_invoice.reference if a.original_invoice else '',
            a.original_product_ref,
            _x(a.refund_amount),
            method_map.get(a.refund_method, a.refund_method),
            a.deposit_client.full_name if a.deposit_client else '',
            (a.notes or '').replace('\n', ' '),
            by,
        ])
    return _csv_text(header, rows)


def _ds_inventory():
    from products.models import Product
    header = ['Référence', 'Nom', 'Statut', 'Catégorie', 'Métal', 'Pureté',
              'Poids brut (g)', 'Poids net (g)', 'Prix/g', 'Valeur matière', 'Coût total', 'Prix vente']
    rows = []
    for p in Product.objects.select_related('category', 'metal_type', 'metal_purity').iterator():
        net = p.net_weight or p.gross_weight or Decimal('0')
        material = p.metal_cost if p.metal_cost else (net * (p.purchase_price_per_gram or Decimal('0')))
        rows.append([
            p.reference, p.name, p.get_status_display(),
            p.category.name if p.category else '',
            p.metal_type.name if p.metal_type else '',
            p.metal_purity.name if p.metal_purity else '',
            _x(p.gross_weight), _x(p.net_weight), _x(p.purchase_price_per_gram),
            _x(material), _x(p.total_cost), _x(p.selling_price),
        ])
    return _csv_text(header, rows)


def _ds_clients():
    from clients.models import Client
    header = ['Code', 'Nom', 'Téléphone', 'Email', 'Créé le']
    rows = []
    for c in Client.objects.iterator():
        rows.append([
            c.code or '', c.full_name, c.phone or '', getattr(c, 'email', '') or '',
            c.created_at.strftime('%Y-%m-%d') if getattr(c, 'created_at', None) else '',
        ])
    return _csv_text(header, rows)


def _ds_deposits():
    from deposits.models import DepositTransaction
    header = ['Date', 'Client', 'Type', 'Montant', 'Solde après', 'Méthode', 'Description']
    rows = []
    for t in DepositTransaction.objects.select_related('account__client', 'payment_method').iterator():
        rows.append([
            (t.date.strftime('%Y-%m-%d') if t.date else (t.created_at.strftime('%Y-%m-%d') if t.created_at else '')),
            t.account.client.full_name if t.account and t.account.client else '',
            t.get_transaction_type_display(),
            _x(t.amount), _x(t.balance_after),
            t.payment_method.name if t.payment_method else '',
            (t.description or '').replace('\n', ' '),
        ])
    return _csv_text(header, rows)


def _period_filtered(request, qs, date_field='date'):
    """Apply the dashboard's period/date filters to a queryset."""
    from django.utils import timezone
    today = timezone.now().date()
    month_start = today.replace(day=1)
    df = request.GET.get('date_from', '')
    dt = request.GET.get('date_to', '')
    period = request.GET.get('period', 'month')
    if df:
        qs = qs.filter(**{f'{date_field}__gte': df})
    elif period == 'today':
        qs = qs.filter(**{date_field: today})
    elif period == 'month':
        qs = qs.filter(**{f'{date_field}__gte': month_start})
    if dt:
        qs = qs.filter(**{f'{date_field}__lte': dt})
    return qs


@login_required(login_url='login')
def sales_export(request):
    """Download a single dashboard dataset as CSV, honoring period/seller filters."""
    if not request.user.is_staff:
        messages.error(request, 'Accès refusé.')
        return redirect('dashboard')

    report = request.GET.get('report', 'invoices')
    seller = request.GET.get('seller', '')

    if report == 'payments':
        from payments.models import ClientPayment
        qs = ClientPayment.objects.filter(sale_invoice__is_deleted=False)
        qs = _period_filtered(request, qs, 'date')
        if seller:
            qs = qs.filter(sale_invoice__seller_id=seller)
        text = _ds_payments(qs.order_by('-date'))
    elif report == 'returns':
        qs = SaleInvoiceAction.objects.filter(action_type=SaleInvoiceAction.ActionType.RETURN)
        qs = _period_filtered(request, qs, 'created_at__date')
        if seller:
            qs = qs.filter(original_invoice__seller_id=seller)
        text = _ds_returns(qs.order_by('-created_at'))
    else:  # invoices
        report = 'invoices'
        qs = SaleInvoice.objects.filter(is_deleted=False)
        qs = _period_filtered(request, qs, 'date')
        if seller:
            qs = qs.filter(seller_id=seller)
        text = _ds_invoices(qs.order_by('-date'))

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('﻿')
    response['Content-Disposition'] = f'attachment; filename="{report}.csv"'
    response.write(text)
    return response


def _run_full_export(job_id):
    """Background worker: build a ZIP of all datasets (all-time) into the job file."""
    import zipfile
    from django.db import connection
    from django.core.files.base import ContentFile
    from django.utils import timezone
    from .models import DataExportJob
    try:
        job = DataExportJob.objects.get(id=job_id)
        job.status = DataExportJob.Status.RUNNING
        job.save(update_fields=['status'])

        datasets = [
            ('factures.csv', _ds_invoices(SaleInvoice.objects.filter(is_deleted=False).order_by('-date'))),
            ('retours.csv', _ds_returns(SaleInvoiceAction.objects.filter(action_type=SaleInvoiceAction.ActionType.RETURN).order_by('-created_at'))),
            ('inventaire.csv', _ds_inventory()),
            ('clients.csv', _ds_clients()),
            ('depots.csv', _ds_deposits()),
        ]
        # Payments separately (import here)
        from payments.models import ClientPayment
        datasets.insert(1, ('paiements.csv', _ds_payments(ClientPayment.objects.all().order_by('-date'))))

        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname, text in datasets:
                zf.writestr(fname, '﻿' + text)
        buf.seek(0)

        job.file.save(f'export_complet_{job.id}.zip', ContentFile(buf.read()), save=False)
        job.status = DataExportJob.Status.DONE
        job.finished_at = timezone.now()
        job.save()
    except Exception as e:
        try:
            job = DataExportJob.objects.get(id=job_id)
            job.status = DataExportJob.Status.FAILED
            job.error = str(e)[:2000]
            job.save(update_fields=['status', 'error'])
        except Exception:
            pass
    finally:
        connection.close()


@login_required(login_url='login')
@require_http_methods(["POST"])
def full_export_start(request):
    """Kick off a background full-data export; returns the job id."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    import threading
    from .models import DataExportJob
    job = DataExportJob.objects.create(created_by=request.user, status=DataExportJob.Status.PENDING)
    t = threading.Thread(target=_run_full_export, args=(job.id,), daemon=True)
    t.start()
    return JsonResponse({'success': True, 'job_id': job.id, 'status': job.status})


@login_required(login_url='login')
def full_export_status(request, job_id):
    """Poll a background export job."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)
    from .models import DataExportJob
    try:
        job = DataExportJob.objects.get(id=job_id)
    except DataExportJob.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Introuvable'}, status=404)
    data = {'success': True, 'status': job.status, 'error': job.error}
    if job.status == DataExportJob.Status.DONE and job.file:
        from django.urls import reverse
        data['download_url'] = reverse('sales:full_export_download', args=[job.id])
    return JsonResponse(data)


@login_required(login_url='login')
def full_export_download(request, job_id):
    """Serve a finished full-data export ZIP."""
    if not request.user.is_staff:
        messages.error(request, 'Accès refusé.')
        return redirect('dashboard')
    from django.http import FileResponse
    from .models import DataExportJob
    job = get_object_or_404(DataExportJob, id=job_id)
    if job.status != DataExportJob.Status.DONE or not job.file:
        messages.error(request, "L'export n'est pas encore prêt.")
        return redirect('sales:sales_dashboard')
    return FileResponse(job.file.open('rb'), as_attachment=True, filename='export_complet.zip')


@login_required(login_url='login')
@require_http_methods(["GET"])
def pending_invoice_detail_api(request, reference):
    """
    JSON metadata for a draft/pending sale (§6): seller, created date, client,
    line items, totals, and full-resolution photo URLs — so the assistant can
    read the receipt photos without scraping the DOM. No OCR is performed here.
    """
    invoice = (SaleInvoice.objects
               .select_related('seller', 'client')
               .prefetch_related('photos', 'items__product')
               .filter(reference=reference, is_deleted=False).first())
    if not invoice:
        return JsonResponse({'ok': False, 'error': f'Facture {reference} introuvable'}, status=404)

    def _abs(url):
        try:
            return request.build_absolute_uri(url)
        except Exception:
            return url

    photos = []
    for ph in invoice.photos.all():
        if getattr(ph, 'image', None):
            try:
                photos.append(_abs(ph.image.url))
            except Exception:
                continue

    items = [{
        'product_id': it.product_id,
        'reference': it.product.reference if it.product else None,
        'name': it.product.name if it.product else None,
        'quantity': str(it.quantity),
        'unit_price': str(it.unit_price) if it.unit_price is not None else None,
        'total': str(it.total_amount) if it.total_amount is not None else None,
    } for it in invoice.items.all()]

    seller = None
    if invoice.seller:
        seller = invoice.seller.get_full_name() or invoice.seller.username
    client = None
    if invoice.client:
        client = {'id': invoice.client.id, 'name': invoice.client.full_name,
                  'phone': invoice.client.phone or ''}

    return JsonResponse({
        'ok': True,
        'id': invoice.id,
        'reference': invoice.reference,
        'status': invoice.status,
        'seller': seller,
        'created_at': invoice.created_at.isoformat() if invoice.created_at else None,
        'date': invoice.date.isoformat() if invoice.date else None,
        'client': client,
        'photos': photos,
        'items': items,
        'subtotal': str(invoice.subtotal) if invoice.subtotal is not None else None,
        'total': str(invoice.total_amount) if invoice.total_amount is not None else None,
    })


@login_required(login_url='login')
@require_http_methods(["POST"])
def pending_invoice_complete_api(request, reference):
    """
    One-shot JSON completion of a draft invoice (§3 of the automation brief).

    Does the whole completion atomically: rename reference, attach/create client,
    add items, set delivery, record payments, reconcile and validate — replacing
    8-12 sequential browser round-trips. Additive: the existing UI flow at
    /sales/pending/<ref>/complete/ is unchanged.

    Body: {reference, items[{product_id|reference, quantity, selling_price}],
           delivery{type, tracking_number, carrier_id?}, client{id|first_name,last_name,phone}?,
           payments[{method_id|method_code, date, amount, reference}], validate}
    """
    import json as _json
    from django.db import transaction
    from datetime import datetime as _dt
    from payments.models import ClientPayment

    def err(http_status, code, message, extra=None):
        e = {'code': code, 'message': message}
        if extra:
            e.update(extra)
        return JsonResponse({'ok': False, 'errors': [e]}, status=http_status)

    try:
        data = _json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return err(400, 'bad_json', 'Corps JSON invalide')

    invoice = SaleInvoice.objects.filter(reference=reference, is_deleted=False).first()
    if not invoice:
        return err(404, 'not_found', f'Facture {reference} introuvable')
    if invoice.status != SaleInvoice.Status.DRAFT:
        return err(409, 'already_completed',
                   f'La facture {invoice.reference} a déjà été validée '
                   f'(statut {invoice.get_status_display()}).')

    items_in = data.get('items') or []
    if not items_in:
        return err(400, 'no_items', 'Au moins un article est requis')

    warnings = []
    client_created = False
    do_validate = bool(data.get('validate', True))
    DELIVERY_MAP = {
        'magasin': 'magasin', 'amana': 'amana',
        'autre_transporteur': 'transporteur', 'transporteur': 'transporteur',
        'en_stock': 'en_stock',
    }

    try:
        with transaction.atomic():
            # --- Reference ---
            new_ref = str(data.get('reference') or '').strip()
            if new_ref and new_ref != invoice.reference:
                if SaleInvoice.objects.filter(reference=new_ref, is_deleted=False).exclude(id=invoice.id).exists():
                    return err(400, 'reference_taken', f'La référence {new_ref} existe déjà.')
                invoice.reference = new_ref

            # --- Client ---
            cb = data.get('client')
            if cb:
                cid = cb.get('id')
                phone = (cb.get('phone') or '').strip()
                if cid:
                    c = Client.objects.filter(pk=cid).first()
                    if not c:
                        return err(400, 'client_not_found', f'Client id={cid} introuvable')
                    invoice.client = c
                elif phone and Client.objects.filter(phone=phone, is_active=True).exists():
                    invoice.client = Client.objects.filter(phone=phone, is_active=True).first()
                    warnings.append({'code': 'client_exists',
                                     'message': f'Un client avec le téléphone {phone} existe déjà; rattaché au lieu de créer un doublon.'})
                else:
                    fn = (cb.get('first_name') or '').strip()
                    ln = (cb.get('last_name') or '').strip()
                    if not (fn and ln and phone):
                        return err(400, 'client_incomplete',
                                   'Pour créer un client: first_name, last_name et phone requis.')
                    invoice.client = Client.objects.create(
                        first_name=fn, last_name=ln, phone=phone, is_active=True)
                    client_created = True

            # Preserve the draft's original date (not today) when completing.
            if not invoice.date:
                invoice.date = invoice.created_at.date() if invoice.created_at else timezone.now().date()
            invoice.save()

            # --- Items ---
            for it in items_in:
                pid = it.get('product_id')
                pref = (it.get('reference') or '').strip()
                product = None
                if pid:
                    product = Product.objects.filter(pk=pid).first()
                elif pref:
                    product = Product.objects.filter(reference=pref).first()
                if not product:
                    return err(400, 'product_not_found',
                               f'Produit introuvable: {pid or pref}', {'item': it})
                if product.status == 'sold':
                    return err(400, 'product_sold',
                               f'Produit déjà vendu: {product.reference}', {'product_id': product.id})
                try:
                    qty = Decimal(str(it.get('quantity', 1)))
                    sp_raw = it.get('selling_price')
                    sp = Decimal(str(sp_raw)) if sp_raw not in (None, '') else Decimal(str(product.selling_price or 0))
                except (InvalidOperation, TypeError):
                    return err(400, 'bad_item_values', f'Valeurs invalides pour {product.reference}')
                if qty <= 0:
                    return err(400, 'bad_quantity', f'Quantité invalide pour {product.reference}')
                SaleInvoiceItem.objects.create(
                    invoice=invoice, product=product, quantity=qty,
                    original_price=product.selling_price or sp,
                    negotiated_price=sp, unit_price=sp,
                    total_amount=sp * qty,
                )

            invoice.calculate_totals()
            invoice.refresh_from_db()

            # --- Payments ---
            total_paid = Decimal('0')
            for i, pay in enumerate(data.get('payments') or []):
                try:
                    amount = Decimal(str(pay.get('amount', '0')))
                except (InvalidOperation, TypeError):
                    return err(400, 'bad_payment_amount', f'Montant invalide (paiement {i + 1})')
                if amount <= 0:
                    continue
                pm = None
                if pay.get('method_id'):
                    pm = PaymentMethod.objects.filter(pk=pay['method_id']).first()
                if not pm and pay.get('method_code'):
                    pm = PaymentMethod.objects.filter(code=pay['method_code']).first()
                if not pm:
                    return err(400, 'payment_method_not_found',
                               f'Mode de paiement introuvable (paiement {i + 1})')
                date_str = (pay.get('date') or '').strip()
                try:
                    pay_date = _dt.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
                except ValueError:
                    pay_date = timezone.now().date()
                pref_pay = (pay.get('reference') or '').strip() or f"PAY-{invoice.reference}-{i + 1}"
                ClientPayment.objects.create(
                    reference=pref_pay, date=pay_date,
                    payment_type=ClientPayment.PaymentType.INVOICE,
                    client=invoice.client, amount=amount, payment_method=pm,
                    sale_invoice=invoice, created_by=request.user,
                )
                total_paid += amount

            # --- Reconcile arithmetic ---
            if total_paid > invoice.total_amount:
                return err(400, 'overpaid',
                           f'Somme des paiements ({total_paid}) supérieure au total ({invoice.total_amount}).',
                           {'total': str(invoice.total_amount), 'total_paid': str(total_paid)})

            recorded = min(total_paid, invoice.total_amount)
            invoice.amount_paid = recorded
            invoice.balance_due = invoice.total_amount - recorded
            if total_paid >= invoice.total_amount and invoice.total_amount > 0:
                invoice.status = SaleInvoice.Status.PAID
                invoice.balance_due = Decimal('0')
            elif total_paid > 0:
                invoice.status = SaleInvoice.Status.PARTIAL_PAID
            else:
                invoice.status = SaleInvoice.Status.UNPAID

            # --- Delivery ---
            db = data.get('delivery') or {}
            dtype = DELIVERY_MAP.get((db.get('type') or 'magasin').strip(), 'magasin')
            invoice.delivery_method_type = dtype
            tracking = (db.get('tracking_number') or '').strip()
            invoice.tracking_number = tracking
            if dtype in ('amana', 'transporteur') and not tracking:
                warnings.append({'code': 'no_tracking',
                                 'message': f'Aucun numéro de suivi fourni pour {dtype}.'})
            if db.get('carrier_id') and dtype == 'transporteur':
                from settings_app.models import Carrier
                inv_carrier = Carrier.objects.filter(pk=db['carrier_id']).first()
                if inv_carrier:
                    invoice.carrier = inv_carrier

            if not do_validate:
                invoice.status = SaleInvoice.Status.DRAFT  # save without validating
            invoice.save()

            if do_validate:
                if dtype in ('amana', 'transporteur'):
                    from sales.models import Delivery
                    Delivery.objects.create(
                        invoice=invoice,
                        client_name=invoice.client.full_name if invoice.client else '',
                        client_phone=invoice.client.phone if invoice.client else '',
                        total_amount=invoice.total_amount, delivery_method_type=dtype,
                        carrier=invoice.carrier, tracking_number=tracking, status='pending',
                    )
                if dtype == 'en_stock' and invoice.client:
                    from stock_storage.models import StockStorageAccount, StockStorageItem
                    acct, _ = StockStorageAccount.objects.get_or_create(
                        client=invoice.client, defaults={'created_by': request.user})
                    for inv_item in invoice.items.select_related('product'):
                        if inv_item.product:
                            StockStorageItem.objects.create(
                                account=acct, invoice=invoice, product=inv_item.product,
                                product_reference=inv_item.product.reference,
                                product_name=inv_item.product.name,
                                product_weight=inv_item.product.gross_weight or 0,
                                price=inv_item.total_amount or 0, created_by=request.user)
                for inv_item in invoice.items.all():
                    if inv_item.product:
                        inv_item.product.status = 'sold'
                        inv_item.product.save(update_fields=['status'])

            ActivityLog.objects.create(
                user=request.user, action=ActivityLog.ActionType.UPDATE,
                model_name='SaleInvoice', object_id=str(invoice.id),
                object_repr=str(invoice),
                details={'action': 'completed_via_api', 'reference': invoice.reference})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception('pending_invoice_complete_api failed')
        return err(500, 'server_error', str(e))

    STATUS_MAP = {'paid': 'PAYEE', 'partial': 'PARTIELLEMENT_PAYEE',
                  'unpaid': 'NON_PAYEE', 'draft': 'BROUILLON'}
    return JsonResponse({
        'ok': True,
        'invoice_id': invoice.id,
        'reference': invoice.reference,
        'status': STATUS_MAP.get(invoice.status, invoice.status.upper()),
        'status_code': invoice.status,
        'subtotal': str(invoice.subtotal),
        'discount': str(invoice.discount_amount),
        'total': str(invoice.total_amount),
        'total_paid': str(invoice.amount_paid),
        'url': f'/sales/invoices/{invoice.reference}/',
        'client': {'id': invoice.client.id if invoice.client else None, 'created': client_created},
        'warnings': warnings,
    })


# ============================================================================
# Product circulation (online-selling flow)
# ============================================================================

def _circulation_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0] if xff else request.META.get('REMOTE_ADDR')


def _product_image_url(product):
    try:
        if product.main_image:
            return product.main_image.url
    except Exception:
        pass
    img = product.images.first()
    return img.image.url if img and img.image else ''


@login_required(login_url='login')
def circulation_list(request):
    """Circulation register: products out with online sellers + history."""
    out_qs = ProductCirculation.objects.filter(
        status=ProductCirculation.Status.OUT
    ).select_related('product', 'seller', 'sent_by').prefetch_related('product__images')

    seller_filter = request.GET.get('seller', '')
    if seller_filter:
        out_qs = out_qs.filter(seller_id=seller_filter)

    search = request.GET.get('search', '').strip()
    if search:
        out_qs = out_qs.filter(
            Q(product__reference__icontains=search) |
            Q(product__name__icontains=search) |
            Q(product__barcode__icontains=search) |
            Q(product__rfid_tag__icontains=search)
        )

    history_qs = ProductCirculation.objects.exclude(
        status=ProductCirculation.Status.OUT
    ).select_related('product', 'seller', 'sent_by', 'returned_by', 'invoice')[:100]

    from django.contrib.auth import get_user_model
    User = get_user_model()
    sellers = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')

    context = {
        'out_items': out_qs,
        'history_items': history_qs,
        'sellers': sellers,
        'stats': {
            'out': ProductCirculation.objects.filter(status=ProductCirculation.Status.OUT).count(),
            'sold': ProductCirculation.objects.filter(status=ProductCirculation.Status.SOLD).count(),
            'returned': ProductCirculation.objects.filter(status=ProductCirculation.Status.RETURNED).count(),
        },
        'seller_filter': seller_filter,
        'search': search,
    }
    return render(request, 'sales/circulation_list.html', context)


@login_required(login_url='login')
def circulation_product_search(request):
    """Search finished products to send out (annotates already-out)."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'products': []})

    products = Product.objects.filter(
        product_type=Product.ProductType.FINISHED
    ).filter(
        Q(reference__icontains=query) |
        Q(barcode__iexact=query) |
        Q(name__icontains=query)
    ).exclude(status='sold').select_related('category')[:20]

    out_ids = set(ProductCirculation.objects.filter(
        product__in=products, status=ProductCirculation.Status.OUT
    ).values_list('product_id', flat=True))

    results = [{
        'id': p.id,
        'reference': p.reference or '',
        'name': p.name or (p.category.name if p.category else 'Produit'),
        'category': p.category.name if p.category else '',
        'image': _product_image_url(p),
        'already_out': p.id in out_ids,
    } for p in products]
    return JsonResponse({'products': results})


@login_required(login_url='login')
def circulation_scan_lookup(request):
    """
    Resolve a scanned barcode to a product. Handles both label generations:
      * new labels = Code128 of the digits kept in sync with Product.barcode,
      * old labels = whatever was stored in Product.barcode / reference.
    Cascade (first hit wins): exact barcode -> exact reference -> exact rfid ->
    digits-only barcode -> loose contains (only auto-picked when unique).
    """
    import re
    code = (request.GET.get('code') or '').strip()
    if not code:
        return JsonResponse({'found': False, 'candidates': []})

    def payload(p):
        return {
            'id': p.id,
            'reference': p.reference or '',
            'name': p.name or (p.category.name if p.category else 'Produit'),
            'image': _product_image_url(p),
            'status': p.get_status_display() if p.status else '',
            'is_sold': p.status == 'sold',
            'already_out': ProductCirculation.objects.filter(
                product=p, status=ProductCirculation.Status.OUT).exists(),
        }

    product = None
    matched = None
    for field, q in (('barcode', Q(barcode__iexact=code)),
                     ('reference', Q(reference__iexact=code)),
                     ('rfid', Q(rfid_tag__iexact=code))):
        product = Product.objects.select_related('category').filter(q).first()
        if product:
            matched = field
            break

    if not product:
        digits = re.sub(r'\D', '', code)
        if digits and digits != code:
            product = Product.objects.select_related('category').filter(barcode__iexact=digits).first()
            if product:
                matched = 'barcode'

    candidates = []
    if not product:
        cands = list(Product.objects.select_related('category').filter(
            Q(barcode__icontains=code) | Q(reference__icontains=code)
        )[:10])
        if len(cands) == 1:
            product, matched = cands[0], 'contains'
        else:
            candidates = cands

    if product:
        return JsonResponse({'found': True, 'matched': matched, 'product': payload(product)})
    return JsonResponse({'found': False, 'code': code,
                         'candidates': [payload(c) for c in candidates]})


@login_required(login_url='login')
@require_http_methods(["POST"])
def circulation_out(request):
    """Mark a product as out (en circulation) with an online seller."""
    product_id = (request.POST.get('product_id') or '').strip()
    reference = (request.POST.get('reference') or '').strip()
    seller_id = (request.POST.get('seller_id') or '').strip()
    notes = (request.POST.get('notes') or '').strip()

    product = None
    if product_id:
        product = Product.objects.filter(id=product_id).first()
    if not product and reference:
        product = Product.objects.filter(
            Q(reference__iexact=reference) | Q(barcode__iexact=reference)
        ).first()

    if not product:
        messages.error(request, "Produit introuvable.")
        return redirect('sales:circulation')

    if ProductCirculation.objects.filter(
        product=product, status=ProductCirculation.Status.OUT
    ).exists():
        messages.warning(request, f"{product.reference} est déjà en circulation.")
        return redirect('sales:circulation')

    if product.status == 'sold':
        messages.error(request, f"{product.reference} est déjà vendu, il ne peut pas circuler.")
        return redirect('sales:circulation')

    seller = None
    if seller_id:
        from django.contrib.auth import get_user_model
        seller = get_user_model().objects.filter(id=seller_id).first()

    circ = ProductCirculation.objects.create(
        product=product,
        seller=seller,
        sent_by=request.user,
        notes=notes,
    )
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.CREATE,
        model_name='ProductCirculation',
        object_id=str(circ.id),
        object_repr=f"Sortie circulation {product.reference}",
        ip_address=_circulation_ip(request),
    )
    messages.success(request, f"{product.reference} mis en circulation.")
    return redirect('sales:circulation')


@login_required(login_url='login')
@require_http_methods(["POST"])
def circulation_return(request, pk):
    """Operator marks a circulating product back in (returned, unsold)."""
    circ = get_object_or_404(ProductCirculation, pk=pk)
    if circ.status != ProductCirculation.Status.OUT:
        messages.warning(request, "Cet article n'est plus en circulation.")
        return redirect('sales:circulation')

    circ.status = ProductCirculation.Status.RETURNED
    circ.returned_by = request.user
    circ.date_back = timezone.now()
    circ.save(update_fields=['status', 'returned_by', 'date_back'])
    ActivityLog.objects.create(
        user=request.user,
        action=ActivityLog.ActionType.UPDATE,
        model_name='ProductCirculation',
        object_id=str(circ.id),
        object_repr=f"Retour vitrine {circ.product.reference}",
        ip_address=_circulation_ip(request),
    )
    messages.success(request, f"{circ.product.reference} de retour en vitrine.")
    return redirect('sales:circulation')


@login_required(login_url='login')
@require_http_methods(["POST"])
def circulation_revert(request, pk):
    """Correction: put a sold/returned record back in circulation."""
    circ = get_object_or_404(ProductCirculation, pk=pk)
    circ.status = ProductCirculation.Status.OUT
    circ.invoice = None
    circ.date_back = None
    circ.returned_by = None
    circ.save(update_fields=['status', 'invoice', 'date_back', 'returned_by'])
    messages.success(request, f"{circ.product.reference} remis en circulation.")
    return redirect('sales:circulation')


# ============================================================================
# Bénéfice (profit report)
# ============================================================================

def _benefice_queryset(request):
    """
    Build the profit queryset (one row per sold line item) from the request
    filters. Returns (queryset, filters_dict). Each row is annotated with
    `bought_price` (product cost x quantity) and `gain` (sale - cost).
    """
    from django.db.models import ExpressionWrapper, DecimalField
    from django.db.models.functions import Coalesce

    money = DecimalField(max_digits=14, decimal_places=2)
    cost_expr = ExpressionWrapper(
        Coalesce(F('product__total_cost'), Decimal('0')) * F('quantity'),
        output_field=money,
    )
    gain_expr = ExpressionWrapper(
        F('total_amount') - Coalesce(F('product__total_cost'), Decimal('0')) * F('quantity'),
        output_field=money,
    )

    qs = (SaleInvoiceItem.objects
          .select_related('invoice', 'product')
          .filter(invoice__is_deleted=False, is_returned=False)
          .exclude(invoice__status__in=['draft', 'cancelled'])
          .annotate(bought_price=cost_expr, gain=gain_expr))

    date_from = (request.GET.get('date_from') or '').strip()
    date_to = (request.GET.get('date_to') or '').strip()
    product_q = (request.GET.get('product') or '').strip()
    invoice_q = (request.GET.get('invoice') or '').strip()

    if date_from:
        qs = qs.filter(invoice__date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice__date__lte=date_to)
    if product_q:
        qs = qs.filter(Q(product__reference__icontains=product_q) |
                       Q(product__name__icontains=product_q))
    if invoice_q:
        qs = qs.filter(invoice__reference__icontains=invoice_q)

    qs = qs.order_by('-invoice__date', '-invoice__created_at', 'id')

    filters = {
        'date_from': date_from, 'date_to': date_to,
        'product': product_q, 'invoice': invoice_q,
    }
    return qs, filters


def _benefice_totals(qs):
    from django.db.models import Sum
    agg = qs.aggregate(
        total_sales=Sum('total_amount'),
        total_cost=Sum('bought_price'),
        total_gain=Sum('gain'),
    )
    total_sales = agg['total_sales'] or Decimal('0')
    total_cost = agg['total_cost'] or Decimal('0')
    total_gain = agg['total_gain'] or Decimal('0')
    margin = (total_gain / total_cost * 100) if total_cost else Decimal('0')
    return {
        'total_sales': total_sales,
        'total_cost': total_cost,
        'total_gain': total_gain,
        'margin': margin,
        'count': qs.count(),
    }


@login_required(login_url='login')
def benefice_report(request):
    """Profit report: one row per sold item with sale/cost/gain + images."""
    qs, filters = _benefice_queryset(request)
    totals = _benefice_totals(qs)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Preserve filters (without page) for pagination + print links
    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    context = {
        'rows': page_obj,
        'page_obj': page_obj,
        'totals': totals,
        'filters': filters,
        'querystring': querystring,
    }
    return render(request, 'sales/benefice_report.html', context)


@login_required(login_url='login')
def benefice_report_print(request):
    """A4 print view: all filtered rows (no pagination) + totals.

    Images are opt-in (?images=1): full-resolution product/invoice photos make
    a large report too heavy to print reliably (and unusable on phones), so the
    default is a clean, multi-page text table.
    """
    qs, filters = _benefice_queryset(request)
    totals = _benefice_totals(qs)
    context = {
        'rows': qs,
        'totals': totals,
        'filters': filters,
        'now': timezone.now(),
        'user': request.user,
        'show_images': request.GET.get('images') == '1',
    }
    return render(request, 'sales/benefice_report_print.html', context)


# ===========================================================================
# Plateau anti-vol (anti-theft tray monitor)
# A dedicated screen with the CF601 reader. Pieces sit on the tray during a
# sale; the page shows which are present, and flags any piece that left the
# tray WITHOUT being sold.
# ===========================================================================

@login_required(login_url='login')
def tray_monitor(request):
    """Dedicated anti-theft tray screen (used with the CF601 in keyboard mode)."""
    return render(request, 'sales/tray_monitor.html', {})


@login_required(login_url='login')
@require_http_methods(["POST"])
def tray_resolve(request):
    """
    Resolve a batch of scanned EPCs to products with their CURRENT status.
    The tray page polls this to know, for each piece it has seen, whether it is
    still available or has been sold (so a removed-but-sold piece is fine, while
    a removed-but-unsold piece is an alert).
    """
    import json as _json
    from products.api_views import _batch_find_products
    try:
        data = _json.loads(request.body or '{}')
    except ValueError:
        data = {}
    epcs = data.get('epcs', [])
    epcs_u = [str(e).strip().upper() for e in epcs if e]
    if not epcs_u:
        return JsonResponse({'products': []})

    found = _batch_find_products(epcs_u)  # {matched_epc: Product}
    by_id = {}
    for epc, p in found.items():
        if p.id in by_id:
            continue
        try:
            img = p.main_image.url if p.main_image else None
        except Exception:
            img = None
        by_id[p.id] = {
            'id': p.id,
            'epc': epc,
            'reference': p.reference,
            'name': p.name or '',
            'category': p.category.name if p.category else '',
            'status': p.status,
            'status_display': p.get_status_display(),
            'is_sold': p.status == 'sold',
            'is_available': p.status == 'available',
            'image': img,
            'price': str(p.selling_price or 0),
        }
    return JsonResponse({'products': list(by_id.values())})


# ===========================================================================
# Rapprochement AMANA (standalone COD reconciliation tool)
# Upload monthly bank statements (Relevé des Opérations), extract the
# 'VERSEMENT CONTRE REMBOURSEMENT QB…MA' credit lines, and show which AMANA
# deliveries have actually been paid (money received) vs not yet. Read-only:
# never modifies any Delivery.
# ===========================================================================

@login_required(login_url='login')
def amana_reconciliation(request):
    """Standalone AMANA COD reconciliation page."""
    from .models import Delivery, AmanaStatement, AmanaStatementLine
    from .amana_reconcile import normalize_ref
    from payments.models import ClientPayment

    month_filter = request.GET.get('month', '')

    statements = AmanaStatement.objects.all()
    if month_filter:
        statements = statements.filter(month=month_filter)
    statements = statements.prefetch_related('lines').order_by('-month', '-uploaded_at')

    # Distinct months for the selector
    all_months = list(
        AmanaStatement.objects.values_list('month', flat=True).distinct().order_by('-month')
    )

    # Build the "encaissé" set from ALL imported statement lines (payment can land
    # in a later month than the shipment, so we match across every statement).
    ref_to_line = {}
    for ln in AmanaStatementLine.objects.select_related('statement').all():
        key = normalize_ref(ln.tracking_ref)
        # keep the first occurrence (earliest) if duplicated across statements
        if key not in ref_to_line:
            ref_to_line[key] = ln
    encaisse_refs = set(ref_to_line.keys())

    # All AMANA deliveries that carry a tracking number.
    # Returned parcels never collect COD, so they are not reconciliation candidates.
    import re as _re
    base_deliveries = (
        Delivery.objects.filter(delivery_method_type='amana')
        .exclude(tracking_number='')
        .exclude(status='returned')
    )
    # Optional filter by the delivery's month (created_at), so a huge backlog can
    # be worked through one month at a time.
    dmonth = request.GET.get('dmonth', '')
    deliveries_qs = base_deliveries
    if _re.match(r'^\d{4}-\d{2}$', dmonth or ''):
        y, m = dmonth.split('-')
        deliveries_qs = deliveries_qs.filter(created_at__year=int(y), created_at__month=int(m))
    deliveries = list(
        deliveries_qs.select_related('invoice', 'invoice__seller').order_by('-created_at')
    )
    delivery_months = [
        dt.strftime('%Y-%m')
        for dt in base_deliveries.dates('created_at', 'month', order='DESC')
    ]

    # Expected COD per delivery (carrier-collected payments on its invoice)
    invoice_ids = [d.invoice_id for d in deliveries if d.invoice_id]
    cod_rows = ClientPayment.objects.filter(
        sale_invoice_id__in=invoice_ids,
        payment_method__collected_by_carrier=True,
    ).values('sale_invoice_id').annotate(t=Sum('amount'))
    cod_by_invoice = {r['sale_invoice_id']: r['t'] for r in cod_rows}

    encaissees, non_encaissees = [], []
    tot_encaisse = Decimal('0')
    tot_pending = Decimal('0')
    nb_mismatch = 0

    for d in deliveries:
        key = normalize_ref(d.tracking_number)
        expected = cod_by_invoice.get(d.invoice_id, Decimal('0'))
        if key in encaisse_refs:
            ln = ref_to_line[key]
            mismatch = expected > 0 and abs(ln.amount - expected) >= Decimal('0.01')
            if mismatch:
                nb_mismatch += 1
            tot_encaisse += ln.amount
            encaissees.append({
                'delivery': d,
                'expected': expected,
                'bank_amount': ln.amount,
                'bank_date': ln.value_date or ln.operation_date,
                'statement': ln.statement,
                'mismatch': mismatch,
            })
        else:
            # Skip deliveries with no AMANA COD to collect (expected == 0):
            # those were paid in caisse, so there is nothing to encaisser.
            if expected <= 0:
                continue
            tot_pending += expected
            non_encaissees.append({'delivery': d, 'expected': expected})

    context = {
        'statements': statements,
        'all_months': all_months,
        'month_filter': month_filter,
        'encaissees': encaissees,
        'non_encaissees': non_encaissees,
        'tot_encaisse': tot_encaisse,
        'tot_pending': tot_pending,
        'nb_encaisse': len(encaissees),
        'nb_pending': len(non_encaissees),
        'nb_mismatch': nb_mismatch,
        'nb_statements': AmanaStatement.objects.count(),
        'delivery_months': delivery_months,
        'dmonth': dmonth,
    }
    return render(request, 'sales/amana_reconciliation.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def amana_mark_encaisse(request):
    """Manually mark a pending AMANA delivery as encaissé (money received),
    without a bank statement. Creates a line in a per-month 'Encaissement manuel'
    statement so it moves to the encaissées bucket. Deduped by tracking ref."""
    import hashlib
    from .models import Delivery, AmanaStatement, AmanaStatementLine
    from .amana_reconcile import normalize_ref
    from payments.models import ClientPayment

    delivery = get_object_or_404(Delivery, pk=request.POST.get('delivery_id'))
    ref = normalize_ref(delivery.tracking_number)
    if not ref:
        return JsonResponse({'error': 'Livraison sans numéro de suivi.'}, status=400)
    if AmanaStatementLine.objects.filter(tracking_ref=ref).exists():
        return JsonResponse({'ok': True, 'already': True})

    expected = Decimal('0')
    if delivery.invoice_id:
        expected = ClientPayment.objects.filter(
            sale_invoice_id=delivery.invoice_id,
            payment_method__collected_by_carrier=True,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    month = delivery.created_at.strftime('%Y-%m') if delivery.created_at else '0000-00'
    sha = hashlib.sha256(f'manual-encaisse-{month}'.encode()).hexdigest()
    stmt, _ = AmanaStatement.objects.get_or_create(
        sha256=sha,
        defaults={'month': month, 'original_filename': 'Encaissement manuel',
                  'uploaded_by': request.user if request.user.is_authenticated else None},
    )
    AmanaStatementLine.objects.create(
        statement=stmt, operation_date='', value_date='', tracking_ref=ref, amount=expected)
    agg = stmt.lines.aggregate(t=Sum('amount'), n=Count('id'))
    stmt.total_amount = agg['t'] or Decimal('0')
    stmt.line_count = agg['n'] or 0
    stmt.save(update_fields=['total_amount', 'line_count'])
    return JsonResponse({'ok': True})


@login_required(login_url='login')
@require_http_methods(["POST"])
def amana_statement_upload(request):
    """Upload one or more statement PDFs, parse and store them (idempotent)."""
    import hashlib
    import re
    import json
    from django.urls import reverse
    from django.contrib import messages
    from .models import AmanaStatement, AmanaStatementLine
    from .amana_reconcile import extract_text, parse_statement_lines, parse_json_statement, normalize_ref

    month = (request.POST.get('month') or '').strip()
    files = request.FILES.getlist('files')

    if not month or not re.match(r'^\d{4}-\d{2}$', month):
        messages.error(request, "Veuillez choisir un mois valide (AAAA-MM).")
        return redirect('sales:amana_reconciliation')
    if not files:
        messages.error(request, "Veuillez sélectionner au moins un fichier (PDF ou JSON).")
        return redirect('sales:amana_reconciliation')

    # Reviewed OCR rows: a human-corrected [{ref, amount}] list from the scanned
    # -statement review screen. When present, use it as the authoritative lines
    # for the single uploaded scan (no re-parsing).
    reviewed_json = request.POST.get('reviewed_rows', '')
    reviewed_lines = None
    if reviewed_json:
        try:
            reviewed_lines = []
            for row in json.loads(reviewed_json):
                ref = normalize_ref(row.get('ref', ''))
                if not ref:
                    continue
                try:
                    amt = Decimal(str(row.get('amount', '0')))
                except (InvalidOperation, ValueError):
                    amt = Decimal('0')
                reviewed_lines.append({
                    'operation_date': row.get('date', ''),
                    'value_date': row.get('date', ''),
                    'tracking_ref': ref,
                    'amount': amt,
                })
        except (ValueError, TypeError):
            reviewed_lines = None

    imported, skipped, failed, dup_total = 0, 0, 0, 0
    # References already stored across ALL statements. A tracking ref = one
    # parcel = one COD remittance, so a ref seen again (overlapping periods) is a
    # duplicate and is dropped, so no total ever counts the same payment twice.
    seen_refs = set(
        normalize_ref(r) for r in AmanaStatementLine.objects.values_list('tracking_ref', flat=True)
    )
    for f in files:
        try:
            data = f.read()
            sha = hashlib.sha256(data).hexdigest()
            if AmanaStatement.objects.filter(sha256=sha).exists():
                skipped += 1
                continue
            import io
            name = (f.name or '').lower()
            is_json = name.endswith('.json') or data.lstrip()[:1] in (b'{', b'[')
            if reviewed_lines is not None:
                lines = reviewed_lines
            elif is_json:
                lines = parse_json_statement(data)
            else:
                lines = parse_statement_lines(extract_text(io.BytesIO(data)))
            # Drop payments already imported (deduplicate by tracking ref).
            unique_lines = []
            for l in lines:
                k = normalize_ref(l['tracking_ref'])
                if k in seen_refs:
                    dup_total += 1
                    continue
                seen_refs.add(k)
                unique_lines.append(l)
            total = sum((l['amount'] for l in unique_lines), Decimal('0'))
            stmt = AmanaStatement.objects.create(
                month=month,
                original_filename=f.name,
                sha256=sha,
                line_count=len(unique_lines),
                total_amount=total,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            AmanaStatementLine.objects.bulk_create([
                AmanaStatementLine(
                    statement=stmt,
                    operation_date=l['operation_date'],
                    value_date=l['value_date'],
                    tracking_ref=l['tracking_ref'],
                    amount=l['amount'],
                ) for l in unique_lines
            ])
            imported += 1
        except Exception as e:
            failed += 1
            messages.error(request, f"Échec de l'import de {f.name} : {e}")

    if imported:
        messages.success(request, f"{imported} relevé(s) importé(s).")
    if dup_total:
        messages.info(request, f"{dup_total} paiement(s) en double ignoré(s) (déjà présents dans un autre relevé).")
    if skipped:
        messages.info(request, f"{skipped} relevé(s) déjà importé(s) (ignoré).")
    return redirect(f"{reverse('sales:amana_reconciliation')}?month={month}")


@login_required(login_url='login')
@require_http_methods(["POST"])
def amana_statement_delete(request, pk):
    """Remove an imported statement (and its lines)."""
    from django.urls import reverse
    from django.contrib import messages
    from .models import AmanaStatement
    stmt = get_object_or_404(AmanaStatement, pk=pk)
    month = stmt.month
    stmt.delete()
    messages.success(request, "Relevé supprimé.")
    return redirect(f"{reverse('sales:amana_reconciliation')}?month={month}")


@login_required(login_url='login')
def amana_ocr_page(request):
    """Review screen for importing a scanned (image) statement via OCR."""
    return render(request, 'sales/amana_ocr.html', {})


def _ocr_job_path(job_id):
    import os
    import tempfile
    return os.path.join(tempfile.gettempdir(), f'amana_ocr_{job_id}.json')


def _run_ocr_job(data, path):
    """Background worker: OCR/AI-read the scan, refine, write result to `path`.
    Runs in a thread so the web request returns immediately (Cloudflare caps
    request time ~100s; a big multi-page scan can exceed that)."""
    import json as _json
    from django.db import connection
    from .amana_ocr import parse_ocr_rows, ai_extract_rows, refine_rows
    from .amana_reconcile import normalize_ref
    from .models import Delivery
    from payments.models import ClientPayment
    try:
        method = 'ia'
        rows = None
        try:
            rows = ai_extract_rows(data)
        except Exception:
            rows = None
        if rows is None:
            method = 'ocr'
            rows = parse_ocr_rows(data)
        deliveries = Delivery.objects.filter(
            delivery_method_type='amana'
        ).exclude(tracking_number='').values('tracking_number', 'invoice_id')
        inv_ids = [d['invoice_id'] for d in deliveries if d['invoice_id']]
        cod_rows = ClientPayment.objects.filter(
            sale_invoice_id__in=inv_ids,
            payment_method__collected_by_carrier=True,
        ).values('sale_invoice_id').annotate(t=Sum('amount'))
        cod_by_invoice = {r['sale_invoice_id']: r['t'] for r in cod_rows}
        delivery_cod = {}
        for d in deliveries:
            key = normalize_ref(d['tracking_number'])
            if key:
                delivery_cod[key] = cod_by_invoice.get(d['invoice_id'], Decimal('0'))
        refined = refine_rows(rows, delivery_cod)
        with open(path, 'w') as fh:
            _json.dump({'status': 'done', 'rows': refined, 'count': len(refined), 'method': method}, fh)
    except Exception as e:
        with open(path, 'w') as fh:
            _json.dump({'status': 'error', 'error': str(e)}, fh)
    finally:
        try:
            connection.close()
        except Exception:
            pass


@login_required(login_url='login')
@require_http_methods(["POST"])
def amana_ocr_analyze(request):
    """Start a background OCR/AI read of the scan; returns a job id to poll."""
    import json as _json
    import uuid
    import threading
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'error': 'Aucun fichier fourni.'}, status=400)
    data = f.read()
    job_id = uuid.uuid4().hex
    path = _ocr_job_path(job_id)
    try:
        with open(path, 'w') as fh:
            _json.dump({'status': 'pending'}, fh)
    except Exception:
        pass
    threading.Thread(target=_run_ocr_job, args=(data, path), daemon=True).start()
    return JsonResponse({'job_id': job_id})


@login_required(login_url='login')
def amana_ocr_status(request):
    """Poll the result of a background OCR job."""
    import os
    import re as _re
    import json as _json
    job = request.GET.get('job', '')
    if not _re.fullmatch(r'[0-9a-f]{32}', job or ''):
        return JsonResponse({'status': 'error', 'error': 'job invalide'}, status=400)
    path = _ocr_job_path(job)
    if not os.path.exists(path):
        return JsonResponse({'status': 'pending'})
    try:
        with open(path) as fh:
            d = _json.load(fh)
    except Exception:
        return JsonResponse({'status': 'pending'})
    if d.get('status') in ('done', 'error'):
        try:
            os.remove(path)
        except Exception:
            pass
    return JsonResponse(d)


@login_required(login_url='login')
@require_http_methods(["POST"])
def amana_ocr_import(request):
    """
    Import a chosen subset of reviewed scan rows (AJAX, no page reload), so the
    user can bank the sure lines now and come back to the uncertain ones later.
    Deduplicates by tracking ref, so repeated/partial imports never double-count.
    """
    import re as _re
    import json as _json
    import uuid
    from .models import AmanaStatement, AmanaStatementLine
    from .amana_reconcile import normalize_ref

    month = (request.POST.get('month') or '').strip()
    if not _re.match(r'^\d{4}-\d{2}$', month or ''):
        return JsonResponse({'error': 'Choisissez un mois valide (AAAA-MM).'}, status=400)
    try:
        rows = _json.loads(request.POST.get('rows', '[]'))
    except (ValueError, TypeError):
        rows = []

    seen = set(normalize_ref(r) for r in AmanaStatementLine.objects.values_list('tracking_ref', flat=True))
    to_add, dup = [], 0
    for row in rows:
        ref = normalize_ref(row.get('ref', '') if isinstance(row, dict) else '')
        if not ref:
            continue
        if ref in seen:
            dup += 1
            continue
        seen.add(ref)
        try:
            amt = Decimal(str(row.get('amount', '0')))
        except (InvalidOperation, ValueError):
            amt = Decimal('0')
        to_add.append({'ref': ref, 'amount': amt, 'date': row.get('date', '')})

    if not to_add:
        return JsonResponse({'imported': 0, 'duplicates': dup})

    stmt = AmanaStatement.objects.create(
        month=month,
        original_filename='Relevé scanné (OCR)',
        sha256=(uuid.uuid4().hex + uuid.uuid4().hex)[:64],
        line_count=len(to_add),
        total_amount=sum((x['amount'] for x in to_add), Decimal('0')),
        uploaded_by=request.user if request.user.is_authenticated else None,
    )
    AmanaStatementLine.objects.bulk_create([
        AmanaStatementLine(statement=stmt, operation_date=x['date'],
                           value_date=x['date'], tracking_ref=x['ref'], amount=x['amount'])
        for x in to_add
    ])
    return JsonResponse({'imported': len(to_add), 'duplicates': dup})
