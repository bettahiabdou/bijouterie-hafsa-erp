"""
Business Intelligence Insights for Bijouterie Hafsa ERP.
Gathers computed metrics from sales data and uses AI to interpret them.
"""

import json
import logging
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.db.models import Count, Sum, Avg, Min, Max, Q, F
from django.db.models.functions import TruncDate, TruncWeek
from django.utils import timezone

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _d(val, places='0.01'):
    """Round a Decimal safely."""
    if val is None:
        return Decimal('0')
    return Decimal(str(val)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def gather_decision_intelligence(period_days=None):
    """
    Decision-first intelligence: not metrics, but what to DO.
    Growth momentum, cash to unlock (corrective), what to buy / stop buying
    (growth), profit efficiency, and clients to win back.
    """
    from sales.models import SaleInvoice, SaleInvoiceItem, ProductCirculation
    from products.models import Product

    now = timezone.now()
    today = now.date()

    base = SaleInvoice.objects.filter(is_deleted=False).exclude(
        status__in=['draft', 'cancelled', 'returned', 'exchanged'])

    def rev_between(d1, d2):
        agg = base.filter(date__gte=d1, date__lt=d2).aggregate(r=Sum('total_amount'), n=Count('id'))
        return _d(agg['r']), agg['n'] or 0

    # ---- Growth momentum: last 30 days vs the 30 before ----
    cur_rev, cur_n = rev_between(today - timedelta(days=30), today + timedelta(days=1))
    prev_rev, prev_n = rev_between(today - timedelta(days=60), today - timedelta(days=30))
    growth_pct = (round((float(cur_rev) - float(prev_rev)) * 100 / float(prev_rev), 1)
                  if float(prev_rev) > 0 else None)
    growth = {
        'cur_rev': cur_rev, 'prev_rev': prev_rev, 'cur_n': cur_n, 'prev_n': prev_n,
        'growth_pct': growth_pct,
        'cur_basket': _d(cur_rev / cur_n) if cur_n else Decimal('0'),
    }

    # ---- Sell-through per category -> buy / stop ----
    available = Product.objects.filter(status='available')
    sold = Product.objects.filter(status='sold')
    avail_by_cat = {r['category__name']: r['n'] for r in
                    available.values('category__name').annotate(n=Count('id'))}
    sold_by_cat = {r['category__name']: r['n'] for r in
                   sold.values('category__name').annotate(n=Count('id'))}
    val_by_cat = {r['category__name']: r['v'] for r in
                  available.values('category__name').annotate(v=Sum('total_cost'))}
    reorder, liquidate = [], []
    for cat in set(list(avail_by_cat) + list(sold_by_cat)):
        if not cat:
            continue
        a = avail_by_cat.get(cat, 0)
        s = sold_by_cat.get(cat, 0)
        st = round(s * 100 / (s + a), 1) if (s + a) > 0 else 0
        if st >= 55 and a <= max(3, int(s * 0.3)):
            reorder.append({'cat': cat, 'sell_through': st, 'in_stock': a, 'sold': s})
        elif st <= 25 and a >= 3:
            liquidate.append({'cat': cat, 'sell_through': st, 'in_stock': a, 'sold': s,
                              'capital': _d(val_by_cat.get(cat) or 0)})
    reorder.sort(key=lambda x: -x['sell_through'])
    liquidate.sort(key=lambda x: -float(x['capital']))

    # ---- Dead stock (capital immobilisé) ----
    dead = available.filter(created_at__lt=now - timedelta(days=180)).aggregate(
        n=Count('id'), cap=Sum('total_cost'), val=Sum('selling_price'))
    dead_stock = {'count': dead['n'] or 0, 'capital': _d(dead['cap']), 'retail': _d(dead['val'])}

    # ---- Cash to unlock (corrective, quantified) ----
    receivables = base.aggregate(b=Sum('balance_due'))['b'] or Decimal('0')
    circ_out_val = ProductCirculation.objects.filter(status='out').aggregate(
        v=Sum('product__selling_price'))['v'] or Decimal('0')
    cash_to_unlock = {
        'receivables': _d(receivables),
        'dead_capital': dead_stock['capital'],
        'circulation_value': _d(circ_out_val),
        'total': _d((receivables or 0) + (dead['cap'] or 0) + (circ_out_val or 0)),
    }

    # ---- Profit efficiency per category (period-scoped) ----
    inv_scope = base.filter(date__gte=today - timedelta(days=period_days)) if period_days else base
    items = SaleInvoiceItem.objects.filter(invoice__in=inv_scope, product__total_cost__gt=0)
    profit_efficiency = []
    for p in items.values('product__category__name').annotate(
            items=Count('id'), cost=Sum('product__total_cost'),
            rev=Sum('total_amount'), w=Sum('product__net_weight')):
        cost = _d(p['cost'])
        rev = _d(p['rev'])
        margin = rev - cost
        wt = float(p['w'] or 0)
        profit_efficiency.append({
            'cat': p['product__category__name'] or '—',
            'items': p['items'],
            'margin': margin,
            'margin_pct': round(float(margin) * 100 / float(cost), 1) if cost > 0 else 0,
            'margin_per_gram': round(float(margin) / wt, 0) if wt > 0 else 0,
        })
    profit_efficiency.sort(key=lambda x: -float(x['margin']))

    # ---- Clients to win back (bought before, silent > 90 days) ----
    win_back = []
    for c in (base.filter(client__isnull=False)
              .values('client__first_name', 'client__last_name', 'client__phone')
              .annotate(spend=Sum('total_amount'), n=Count('id'), last=Max('date'))):
        if c['last'] and (today - c['last']).days > 90:
            win_back.append({
                'name': f"{c['client__first_name'] or ''} {c['client__last_name'] or ''}".strip() or '—',
                'phone': c['client__phone'] or '',
                'spend': _d(c['spend']),
                'orders': c['n'],
                'days': (today - c['last']).days,
            })
    win_back.sort(key=lambda x: -float(x['spend']))

    return {
        'growth': growth,
        'reorder': reorder[:8],
        'liquidate': liquidate[:8],
        'dead_stock': dead_stock,
        'cash_to_unlock': cash_to_unlock,
        'profit_efficiency': profit_efficiency[:10],
        'win_back': win_back[:10],
    }


def _wa_number(phone):
    """Normalize a Moroccan/intl phone to wa.me digits, or '' if unusable."""
    if not phone:
        return ''
    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    if not digits:
        return ''
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('0') and len(digits) == 10:      # local 06/05/07 -> 212...
        digits = '212' + digits[1:]
    return digits


def _seasonal_note(today):
    """Deterministic Moroccan-jewelry seasonal guidance by month."""
    m = today.month
    if m in (6, 7, 8, 9):
        return {'season': 'Saison des mariages (été)',
                'advice': 'Pic trousseau : privilégier Sertla, Demlij, ensembles et pièces lourdes. Ne pas tomber en rupture sur le haut de gamme mariage.'}
    if m in (3, 4, 5):
        return {'season': 'Pré-saison mariages',
                'advice': 'Reconstituer le stock trousseau (Sertla, Demlij, ensembles) avant l’été. Anticiper la hausse de la demande.'}
    if m in (11, 12):
        return {'season': 'Fêtes de fin d’année',
                'advice': 'Demande de cadeaux : pièces accessibles (bagues, pendentifs, boucles légères), bon moment pour écouler le stock moyen.'}
    return {'season': 'Période plus calme (hiver)',
            'advice': 'Écouler le stock ancien et préparer le printemps. Surveiller le calendrier lunaire pour anticiper Ramadan / Aïd (pics cadeaux).'}


def gather_dashboard(period_days=None):
    """
    Decision cockpit data: health score vs targets, an actionable decision
    queue (with links/WhatsApp), SKU-level lists (with photos), money
    position, monthly trend, and seasonal guidance.
    """
    from urllib.parse import quote
    from django.db.models.functions import TruncMonth
    from sales.models import SaleInvoice, SaleInvoiceItem, ProductCirculation, SalesTarget
    from products.models import Product
    from clients.models import Client
    from deposits.models import DepositTransaction

    now = timezone.now()
    today = now.date()
    d30 = today - timedelta(days=30)
    d60 = today - timedelta(days=60)

    base = SaleInvoice.objects.filter(is_deleted=False).exclude(
        status__in=['draft', 'cancelled', 'returned', 'exchanged'])

    cur = base.filter(date__gte=d30).aggregate(r=Sum('total_amount'), n=Count('id'))
    prev = base.filter(date__gte=d60, date__lt=d30).aggregate(r=Sum('total_amount'))
    rev30 = _d(cur['r'])
    prev30 = _d(prev['r'])
    n30 = cur['n'] or 0
    growth_pct = (round((float(rev30) - float(prev30)) * 100 / float(prev30), 1)
                  if float(prev30) > 0 else None)

    items30 = SaleInvoiceItem.objects.filter(invoice__in=base.filter(date__gte=d30),
                                             product__total_cost__gt=0)
    magg = items30.aggregate(c=Sum('product__total_cost'), r=Sum('total_amount'))
    mcost = _d(magg['c'])
    mrev = _d(magg['r'])
    margin_pct = round(float(mrev - mcost) * 100 / float(mcost), 1) if mcost > 0 else 0
    new_clients30 = Client.objects.filter(created_at__gte=d30).count()

    # ---- Targets ----
    t = SalesTarget.get_current()
    rev_target = _d(t.revenue_target) if (t and t.revenue_target) else (prev30 if prev30 > 0 else rev30)
    margin_target = float(t.margin_target) if t else 18.0
    clients_target = (t.new_clients_target if (t and t.new_clients_target) else 0)
    targets = {'revenue': rev_target, 'margin': margin_target, 'new_clients': clients_target,
               'is_set': bool(t)}

    def clamp(v):
        return max(0, min(100, int(round(v))))

    prog = {
        'revenue': clamp(float(rev30) * 100 / float(rev_target)) if float(rev_target) > 0 else 0,
        'margin': clamp(margin_pct * 100 / margin_target) if margin_target > 0 else 0,
        'new_clients': (clamp(new_clients30 * 100 / clients_target) if clients_target else None),
        'cur': {'revenue': rev30, 'margin': margin_pct, 'new_clients': new_clients30},
    }

    # ---- Money position ----
    available = Product.objects.filter(status='available')
    stock_capital = available.aggregate(v=Sum('total_cost'))['v'] or Decimal('0')
    receivables = base.aggregate(b=Sum('balance_due'))['b'] or Decimal('0')
    deposits_owed = DepositTransaction.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    dead = available.filter(created_at__lt=now - timedelta(days=180)).aggregate(
        n=Count('id'), cap=Sum('total_cost'))
    circ_val = ProductCirculation.objects.filter(status='out').aggregate(
        v=Sum('product__selling_price'))['v'] or Decimal('0')
    money = {
        'stock_capital': _d(stock_capital),
        'receivables': _d(receivables),
        'deposits_owed': _d(deposits_owed),
        'dead_capital': _d(dead['cap']),
        'circulation_value': _d(circ_val),
        'unlockable': _d((receivables or 0) + (dead['cap'] or 0) + (circ_val or 0)),
    }

    # ---- Health score ----
    comps = []
    comps.append(('Marge', clamp(margin_pct * 100 / margin_target) if margin_target > 0 else 50))
    comps.append(('CA vs objectif', clamp(float(rev30) * 100 / float(rev_target)) if float(rev_target) > 0 else 50))
    comps.append(('Croissance', 50 if growth_pct is None else clamp(50 + growth_pct)))
    dead_ratio = float(dead['cap'] or 0) * 100 / float(stock_capital) if stock_capital > 0 else 0
    comps.append(('Stock sain', clamp(100 - dead_ratio * 2)))
    recv_ratio = float(receivables) * 100 / float(rev30) if float(rev30) > 0 else 0
    comps.append(('Encaissement', clamp(100 - recv_ratio)))
    health = int(round(sum(s for _, s in comps) / len(comps)))
    weakest = [name for name, _ in sorted(comps, key=lambda x: x[1])[:2]]

    # ---- Decision queue (actionable) ----
    intel = gather_decision_intelligence(period_days)
    decisions = []
    for r in intel['reorder'][:3]:
        decisions.append({'sev': 'grow', 'icon': 'fa-cart-plus',
            'title': f"Réapprovisionner {r['cat']}",
            'detail': f"Écoulement {r['sell_through']}% — il ne reste que {r['in_stock']} en stock.",
            'cta': 'Créer commande', 'url': '/purchases/orders/create/', 'wa': False})
    if dead['n']:
        decisions.append({'sev': 'fix', 'icon': 'fa-tags',
            'title': f"Écouler {dead['n']} pièces dormantes (>180j)",
            'detail': f"{_d(dead['cap'])} DH de capital immobilisé à débloquer.",
            'cta': 'Voir les pièces', 'url': '/products/?min_age=180', 'wa': False})
    if receivables and receivables > 0:
        decisions.append({'sev': 'fix', 'icon': 'fa-hand-holding-dollar',
            'title': f"Encaisser {_d(receivables)} DH de créances",
            'detail': "Factures avec solde dû non réglé.",
            'cta': 'Voir factures', 'url': '/sales/', 'wa': False})
    for w in intel['win_back'][:3]:
        wa = _wa_number(w['phone'])
        msg = quote(f"Bonjour {w['name']}, c'est Bijouterie Hafsa. Nous avons de nouvelles pièces qui pourraient vous plaire. Passez nous voir !")
        decisions.append({'sev': 'grow', 'icon': 'fa-whatsapp',
            'title': f"Relancer {w['name']}",
            'detail': f"{w['spend']} DH dépensés, silencieux depuis {w['days']}j.",
            'cta': 'WhatsApp', 'url': (f"https://wa.me/{wa}?text={msg}" if wa else None), 'wa': True})

    # ---- SKU-level: dead stock with photos ----
    def _img(p):
        try:
            if p.main_image:
                return p.main_image.url
        except Exception:
            pass
        im = p.images.first() if hasattr(p, 'images') else None
        try:
            return im.image.url if im and im.image else None
        except Exception:
            return None

    dead_skus = []
    for p in (available.filter(created_at__lt=now - timedelta(days=180))
              .select_related('category').prefetch_related('images')
              .order_by('-selling_price')[:12]):
        dead_skus.append({
            'reference': p.reference, 'name': p.name or '',
            'category': p.category.name if p.category else '',
            'price': _d(p.selling_price), 'image': _img(p),
            'days': (today - p.created_at.date()).days if p.created_at else 0,
        })

    restock_skus = []
    for p in (Product.objects.filter(status='sold')
              .select_related('category').prefetch_related('images')
              .order_by('-updated_at')[:8]):
        img = _img(p)
        if not img:
            continue
        restock_skus.append({
            'reference': p.reference, 'name': p.name or '',
            'category': p.category.name if p.category else '',
            'price': _d(p.selling_price), 'image': img,
        })
        if len(restock_skus) >= 6:
            break

    # ---- Win-back with WhatsApp links ----
    win_back = []
    for w in intel['win_back']:
        wa = _wa_number(w['phone'])
        msg = quote(f"Bonjour {w['name']}, c'est Bijouterie Hafsa. Nous avons de nouvelles pièces qui pourraient vous plaire. Passez nous voir !")
        win_back.append({**w, 'wa_url': (f"https://wa.me/{wa}?text={msg}" if wa else None)})

    # ---- Monthly trend (last ~7 months) ----
    months = list(base.filter(date__gte=today - timedelta(days=215))
                  .annotate(m=TruncMonth('date')).values('m')
                  .annotate(r=Sum('total_amount')).order_by('m'))
    trend = [{'label': mm['m'].strftime('%b'), 'rev': float(mm['r'] or 0)} for mm in months if mm['m']]
    trend_max = max((x['rev'] for x in trend), default=0) or 1

    import math
    health_circ = 2 * math.pi * 52
    health_offset = round(health_circ * (1 - health / 100), 1)

    return {
        'health': health,
        'health_offset': health_offset,
        'health_components': [{'name': n, 'score': s} for n, s in comps],
        'health_weakest': weakest,
        'rev30': rev30, 'prev30': prev30, 'n30': n30, 'growth_pct': growth_pct,
        'margin_pct': margin_pct, 'new_clients30': new_clients30,
        'targets': targets, 'progress': prog,
        'money': money,
        'decisions': decisions,
        'dead_skus': dead_skus,
        'restock_skus': restock_skus,
        'win_back': win_back[:10],
        'trend': trend, 'trend_max': trend_max,
        'seasonal': _seasonal_note(today),
    }


def gather_business_data(period_days=None):
    """
    Gather comprehensive business metrics from sales data.
    Returns a dict of computed insights ready for display and AI interpretation.
    """
    from sales.models import SaleInvoice, SaleInvoiceItem
    from products.models import Product
    from clients.models import Client
    from payments.models import ClientPayment

    now = timezone.now()
    today = now.date()

    # Base querysets
    base_qs = SaleInvoice.objects.filter(
        is_deleted=False
    ).exclude(status__in=['draft', 'cancelled', 'returned', 'exchanged'])

    if period_days:
        date_from = today - timedelta(days=period_days)
        base_qs = base_qs.filter(date__gte=date_from)

    items_qs = SaleInvoiceItem.objects.filter(
        invoice__in=base_qs
    )

    # ===== 1. OVERVIEW =====
    total_count = base_qs.count()
    overview_agg = base_qs.aggregate(
        revenue=Sum('total_amount'),
        paid=Sum('amount_paid'),
        balance=Sum('balance_due'),
        avg_basket=Avg('total_amount'),
        date_first=Min('date'),
        date_last=Max('date'),
    )
    with_client = base_qs.filter(client__isnull=False).count()
    without_client = base_qs.filter(client__isnull=True).count()
    rev_client = base_qs.filter(client__isnull=False).aggregate(t=Sum('total_amount'))['t'] or 0
    rev_anon = base_qs.filter(client__isnull=True).aggregate(t=Sum('total_amount'))['t'] or 0

    overview = {
        'total_invoices': total_count,
        'total_revenue': _d(overview_agg['revenue']),
        'avg_basket': _d(overview_agg['avg_basket']),
        'date_first': str(overview_agg['date_first'] or ''),
        'date_last': str(overview_agg['date_last'] or ''),
        'with_client': with_client,
        'without_client': without_client,
        'anonymous_pct': round(without_client * 100 / total_count, 1) if total_count else 0,
        'revenue_client': _d(rev_client),
        'revenue_anonymous': _d(rev_anon),
    }

    # ===== 2. CATEGORY PERFORMANCE =====
    category_raw = list(items_qs.filter(
        product__category__isnull=False
    ).values('product__category__name').annotate(
        items_sold=Count('id'),
        revenue=Sum('total_amount'),
        avg_weight=Avg('product__net_weight'),
    ).order_by('-revenue'))

    total_rev = overview_agg['revenue'] or Decimal('1')
    categories = []
    for c in category_raw:
        rev = c['revenue'] or Decimal('0')
        count = c['items_sold'] or 0
        avg_price = _d(rev / count) if count > 0 else Decimal('0')
        avg_w = _d(c['avg_weight'], '0.1') if c['avg_weight'] else Decimal('0')
        pct = round(float(rev) * 100 / float(total_rev), 1) if float(total_rev) > 0 else 0
        categories.append({
            'name': c['product__category__name'],
            'items_sold': count,
            'revenue': _d(rev),
            'avg_price': avg_price,
            'avg_weight_g': avg_w,
            'pct_revenue': pct,
        })

    # ===== 3. CATEGORY WEIGHT RANGE ANALYSIS =====
    # Which weight ranges sell best per top category
    weight_ranges = []
    for cat in categories[:6]:
        cat_items = items_qs.filter(
            product__category__name=cat['name'],
            product__net_weight__gt=0
        ).values_list('product__net_weight', 'total_amount')

        buckets = defaultdict(lambda: {'count': 0, 'revenue': Decimal('0')})
        for weight, amount in cat_items:
            w = float(weight or 0)
            if w <= 10:
                bucket = '0-10g'
            elif w <= 30:
                bucket = '10-30g'
            elif w <= 50:
                bucket = '30-50g'
            elif w <= 80:
                bucket = '50-80g'
            else:
                bucket = '80g+'
            buckets[bucket]['count'] += 1
            buckets[bucket]['revenue'] += amount or Decimal('0')

        best_bucket = max(buckets.items(), key=lambda x: x[1]['revenue']) if buckets else None
        if best_bucket:
            weight_ranges.append({
                'category': cat['name'],
                'best_range': best_bucket[0],
                'best_range_count': best_bucket[1]['count'],
                'best_range_revenue': _d(best_bucket[1]['revenue']),
                'all_ranges': {k: {'count': v['count'], 'revenue': _d(v['revenue'])} for k, v in sorted(buckets.items())},
            })

    # ===== 4. TOP CLIENTS =====
    top_clients = list(
        base_qs.filter(client__isnull=False)
        .values('client__first_name', 'client__last_name', 'client__phone')
        .annotate(
            invoice_count=Count('id'),
            total_revenue=Sum('total_amount'),
            last_purchase=Max('date'),
        ).order_by('-total_revenue')[:20]
    )
    for cl in top_clients:
        cl['total_revenue'] = _d(cl['total_revenue'])

    # ===== 5. CLIENT FREQUENCY =====
    client_counts = list(
        base_qs.filter(client__isnull=False)
        .values('client_id')
        .annotate(inv_count=Count('id'))
        .values_list('inv_count', flat=True)
    )
    freq = {'1_time': 0, '2_times': 0, '3_plus': 0}
    for c in client_counts:
        if c == 1:
            freq['1_time'] += 1
        elif c == 2:
            freq['2_times'] += 1
        else:
            freq['3_plus'] += 1
    total_unique_clients = len(client_counts)

    client_stats = {
        'total_unique': total_unique_clients,
        'frequency': freq,
        'one_time_pct': round(freq['1_time'] * 100 / total_unique_clients, 1) if total_unique_clients else 0,
        'repeat_clients': list(
            base_qs.filter(client__isnull=False)
            .values('client__first_name', 'client__last_name', 'client__phone')
            .annotate(inv_count=Count('id'), revenue=Sum('total_amount'))
            .filter(inv_count__gte=2)
            .order_by('-inv_count')[:15]
        ),
    }

    # ===== 6. STOCK AGING =====
    available = Product.objects.filter(status='available')
    stock_aging_by_cat = list(
        available.filter(category__isnull=False)
        .values('category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    stock_aging = {
        '0_30d': available.filter(created_at__gte=now - timedelta(days=30)).count(),
        '31_60d': available.filter(created_at__lt=now - timedelta(days=30), created_at__gte=now - timedelta(days=60)).count(),
        '60d_plus': available.filter(created_at__lt=now - timedelta(days=60)).count(),
        'total_available': available.count(),
        'by_category': stock_aging_by_cat,
    }

    # ===== 7. SELL-THROUGH RATE =====
    # Per category: (sold / (sold + available)) — how fast things move
    sell_through = []
    for cat in categories[:10]:
        cat_name = cat['name']
        sold_count = Product.objects.filter(category__name=cat_name, status='sold').count()
        avail_count = Product.objects.filter(category__name=cat_name, status='available').count()
        total_cat = sold_count + avail_count
        rate = round(sold_count * 100 / total_cat, 1) if total_cat > 0 else 0
        sell_through.append({
            'category': cat_name,
            'sold': sold_count,
            'available': avail_count,
            'sell_through_pct': rate,
        })

    # ===== 8. DELIVERY CHANNEL ANALYSIS =====
    delivery_data = list(base_qs.values('delivery_method_type').annotate(
        count=Count('id'),
        revenue=Sum('total_amount'),
        with_client=Count('id', filter=Q(client__isnull=False)),
        anonymous=Count('id', filter=Q(client__isnull=True)),
    ).order_by('-revenue'))

    # ===== 9. DAILY REVENUE TREND (last 30 days) =====
    thirty_days_ago = today - timedelta(days=30)
    daily_trend = list(
        base_qs.filter(date__gte=thirty_days_ago)
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(revenue=Sum('total_amount'), count=Count('id'))
        .order_by('day')
    )

    # ===== 10. DATA QUALITY ALERTS =====
    zero_price_products = Product.objects.filter(
        status='sold',
        purchase_price_per_gram=0
    ).count()
    total_sold = Product.objects.filter(status='sold').count()

    data_quality = {
        'zero_purchase_price': zero_price_products,
        'zero_price_pct': round(zero_price_products * 100 / total_sold, 1) if total_sold else 0,
        'total_sold': total_sold,
    }

    # ===== 11. DAY-OF-WEEK PATTERNS =====
    from django.db.models.functions import ExtractWeekDay
    dow_data = list(
        base_qs.annotate(dow=ExtractWeekDay('date'))
        .values('dow')
        .annotate(count=Count('id'), revenue=Sum('total_amount'), avg_basket=Avg('total_amount'))
        .order_by('dow')
    )
    dow_names = {1: 'Dimanche', 2: 'Lundi', 3: 'Mardi', 4: 'Mercredi', 5: 'Jeudi', 6: 'Vendredi', 7: 'Samedi'}
    day_of_week = [{'day': dow_names.get(d['dow'], d['dow']), 'count': d['count'], 'revenue': _d(d['revenue']), 'avg_basket': _d(d['avg_basket'])} for d in dow_data]

    # ===== 12. CATEGORY x CLIENT TYPE (anonymous vs identified) =====
    cat_client_type = list(items_qs.filter(
        product__category__isnull=False
    ).values('product__category__name').annotate(
        total_rev=Sum('total_amount'),
        client_rev=Sum('total_amount', filter=Q(invoice__client__isnull=False)),
        anon_rev=Sum('total_amount', filter=Q(invoice__client__isnull=True)),
        client_count=Count('id', filter=Q(invoice__client__isnull=False)),
        anon_count=Count('id', filter=Q(invoice__client__isnull=True)),
    ).order_by('-total_rev')[:10])

    # ===== 13. CO-PURCHASE PATTERNS (what categories are bought together) =====
    from itertools import combinations
    co_purchase = defaultdict(int)
    invoices_with_items = base_qs.filter(items__product__category__isnull=False).prefetch_related('items__product__category').distinct()[:500]
    for inv in invoices_with_items:
        cats = list(set(
            item.product.category.name for item in inv.items.all()
            if item.product and item.product.category
        ))
        for pair in combinations(sorted(cats), 2):
            co_purchase[pair] += 1
    top_co_purchases = sorted(co_purchase.items(), key=lambda x: -x[1])[:10]

    # ===== 14. REPEAT CLIENT CATEGORY PREFERENCE =====
    repeat_client_ids = list(
        base_qs.filter(client__isnull=False)
        .values('client_id')
        .annotate(inv_count=Count('id'))
        .filter(inv_count__gte=2)
        .values_list('client_id', flat=True)
    )
    repeat_cat_pref = list(
        items_qs.filter(invoice__client_id__in=repeat_client_ids, product__category__isnull=False)
        .values('product__category__name')
        .annotate(count=Count('id'), revenue=Sum('total_amount'))
        .order_by('-revenue')[:10]
    )

    # ===== 15. PRICE DISTRIBUTION PER CATEGORY =====
    price_distribution = []
    for cat in categories[:8]:
        cat_prices = list(items_qs.filter(
            product__category__name=cat['name']
        ).values_list('total_amount', flat=True))
        if cat_prices:
            sorted_prices = sorted(float(p) for p in cat_prices if p)
            n = len(sorted_prices)
            price_distribution.append({
                'category': cat['name'],
                'min': sorted_prices[0] if sorted_prices else 0,
                'p25': sorted_prices[n // 4] if n > 3 else sorted_prices[0],
                'median': sorted_prices[n // 2] if n > 1 else sorted_prices[0],
                'p75': sorted_prices[3 * n // 4] if n > 3 else sorted_prices[-1],
                'max': sorted_prices[-1] if sorted_prices else 0,
                'count': n,
            })

    # ===== 16. WEEKLY TREND (revenue per week) =====
    weekly_trend = list(
        base_qs.annotate(week=TruncWeek('date'))
        .values('week')
        .annotate(revenue=Sum('total_amount'), count=Count('id'), avg_basket=Avg('total_amount'))
        .order_by('week')
    )

    # ===== PROFITABILITY (products with known costs) =====
    # Use product.total_cost (metal + labor + stones + other), not just metal cost
    profitable_items = items_qs.filter(
        product__total_cost__gt=0,
    ).values(
        'product__category__name',
    ).annotate(
        items=Count('id'),
        total_cost=Sum('product__total_cost'),
        total_revenue=Sum('total_amount'),
    ).order_by('-total_revenue')

    profitability = []
    for p in profitable_items:
        cost = _d(p['total_cost'])
        rev = _d(p['total_revenue'])
        margin = rev - cost
        margin_pct = round(float(margin) * 100 / float(cost), 1) if cost > 0 else 0
        profitability.append({
            'category': p['product__category__name'],
            'items': p['items'],
            'total_cost': cost,
            'total_revenue': rev,
            'margin': margin,
            'margin_pct': margin_pct,
        })

    # ===== 17. CIRCULATION (vente en ligne) =====
    from sales.models import ProductCirculation
    circ_out = ProductCirculation.objects.filter(status='out')
    sold_count = ProductCirculation.objects.filter(status='sold').count()
    ret_count = ProductCirculation.objects.filter(status='returned').count()
    out_count = circ_out.count()
    conv_base = sold_count + ret_count
    circulation = {
        'out_count': out_count,
        'sold_count': sold_count,
        'returned_count': ret_count,
        'conversion_pct': round(sold_count * 100 / conv_base, 1) if conv_base else 0,
        'out_over_30d': circ_out.filter(date_out__lt=now - timedelta(days=30)).count(),
        'out_last_7d': circ_out.filter(date_out__gte=now - timedelta(days=7)).count(),
        'by_seller': [
            {'name': f"{r['seller__first_name'] or ''} {r['seller__last_name'] or ''}".strip() or '—',
             'out': r['n']}
            for r in circ_out.values('seller__first_name', 'seller__last_name')
            .annotate(n=Count('id')).order_by('-n')[:8]
        ],
    }

    # ===== 18. CLIENT DEPOSITS (dépôts) =====
    from deposits.models import DepositAccount, DepositTransaction
    dep_total = DepositTransaction.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    dep_accounts = DepositAccount.objects.count()
    deposits_mod = {
        'total_held': _d(dep_total),
        'account_count': dep_accounts,
        'by_seller': [
            {'name': f"{r['account__managed_by__first_name'] or ''} {r['account__managed_by__last_name'] or ''}".strip() or '—',
             'balance': _d(r['bal']), 'accounts': r['n']}
            for r in DepositTransaction.objects.values(
                'account__managed_by__first_name', 'account__managed_by__last_name'
            ).annotate(bal=Sum('amount'), n=Count('account', distinct=True)).order_by('-bal')[:8]
        ],
        'top_balances': [
            {'name': f"{r['client__first_name'] or ''} {r['client__last_name'] or ''}".strip() or '—',
             'balance': _d(r['bal'])}
            for r in DepositAccount.objects.annotate(bal=Sum('transactions__amount'))
            .filter(bal__gt=0).order_by('-bal')
            .values('client__first_name', 'client__last_name', 'bal')[:8]
        ],
    }

    # ===== 19. SELLER PERFORMANCE =====
    circ_sold_by_seller = dict(
        ProductCirculation.objects.filter(status='sold')
        .values_list('seller__id').annotate(n=Count('id'))
    )
    sellers = []
    for s in (base_qs.filter(seller__isnull=False)
              .values('seller__id', 'seller__first_name', 'seller__last_name')
              .annotate(revenue=Sum('total_amount'), invoices=Count('id'))
              .order_by('-revenue')[:12]):
        sellers.append({
            'name': f"{s['seller__first_name'] or ''} {s['seller__last_name'] or ''}".strip() or '—',
            'revenue': _d(s['revenue']),
            'invoices': s['invoices'],
            'circ_sold': circ_sold_by_seller.get(s['seller__id'], 0),
        })

    # ===== 20. INVENTORY HEALTH (blocs & dernier contrôle) =====
    from products.models import ProductBlock, StockCountSession
    last_session = StockCountSession.objects.filter(status='closed').order_by('-finished_at').first()
    inv_last = None
    if last_session:
        try:
            from products.views import _stock_count_report
            rep = _stock_count_report(last_session)
            inv_last = {
                'id': last_session.id,
                'mode': last_session.get_mode_display(),
                'date': str(last_session.finished_at.date()) if last_session.finished_at else '',
                'expected': rep.get('expected_total', 0),
                'scanned': rep.get('scanned_total', 0),
                'missing': rep.get('missing_count', 0),
                'anomalies': rep.get('anomaly_count', 0),
            }
        except Exception:
            inv_last = None
    inventory_health = {
        'blocks_count': ProductBlock.objects.filter(is_active=True).count(),
        'available_total': available.count(),
        'last_session': inv_last,
    }

    # ===== 21. AGED STOCK (valorisé) + PROFIT TOTALS + RECEIVABLES =====
    def _aged(days):
        agg = available.filter(created_at__lt=now - timedelta(days=days)).aggregate(
            n=Count('id'), val=Sum('selling_price'))
        return {'count': agg['n'] or 0, 'value': _d(agg['val'])}
    aged_stock = {'over_180d': _aged(180), 'over_365d': _aged(365)}

    prof_agg = items_qs.filter(product__total_cost__gt=0).aggregate(
        cost=Sum('product__total_cost'), rev=Sum('total_amount'))
    p_cost = _d(prof_agg['cost'])
    p_rev = _d(prof_agg['rev'])
    p_margin = p_rev - p_cost
    profit_totals = {
        'total_cost': p_cost, 'total_revenue': p_rev, 'total_margin': p_margin,
        'margin_pct': round(float(p_margin) * 100 / float(p_cost), 1) if p_cost > 0 else 0,
    }

    receivables = SaleInvoice.objects.filter(is_deleted=False).exclude(
        status__in=['draft', 'cancelled', 'returned', 'exchanged']
    ).aggregate(bal=Sum('balance_due'))['bal'] or Decimal('0')
    receivables = _d(receivables)

    # ===== 22. ACTION CENTER (décisions prioritaires) =====
    actions = []
    if aged_stock['over_365d']['count']:
        actions.append({'sev': 'high', 'icon': 'fa-hourglass-end',
            'title': f"{aged_stock['over_365d']['count']} pièces en stock depuis plus de 365 jours",
            'detail': f"Valeur immobilisée {aged_stock['over_365d']['value']} DH. Remise ou vérifier des sorties non déclarées.",
            'link': '/products/?min_age=365'})
    elif aged_stock['over_180d']['count']:
        actions.append({'sev': 'medium', 'icon': 'fa-hourglass-half',
            'title': f"{aged_stock['over_180d']['count']} pièces en stock depuis plus de 180 jours",
            'detail': f"Valeur {aged_stock['over_180d']['value']} DH à surveiller.",
            'link': '/products/?min_age=180'})
    if circulation['out_over_30d']:
        actions.append({'sev': 'medium', 'icon': 'fa-truck',
            'title': f"{circulation['out_over_30d']} pièces en circulation depuis plus de 30 jours",
            'detail': "Relancer les vendeuses pour vente ou retour en vitrine.",
            'link': '/sales/circulation/'})
    if receivables > 0:
        actions.append({'sev': 'medium', 'icon': 'fa-hand-holding-dollar',
            'title': f"Créances clients : {receivables} DH",
            'detail': "Solde dû sur factures non réglées.", 'link': '/sales/'})
    if dep_total > 0:
        actions.append({'sev': 'info', 'icon': 'fa-piggy-bank',
            'title': f"Dépôts clients détenus : {_d(dep_total)} DH",
            'detail': f"{dep_accounts} compte(s) — engagement envers les clients.", 'link': '/deposits/'})
    if inv_last and (inv_last['missing'] or inv_last['anomalies']):
        actions.append({'sev': 'high' if inv_last['missing'] else 'medium', 'icon': 'fa-clipboard-check',
            'title': f"Dernier contrôle : {inv_last['missing']} manquant(s), {inv_last['anomalies']} anomalie(s)",
            'detail': "Vérifier les écarts (démarque/vol ou statut non mis à jour).",
            'link': f"/products/stock-count/{inv_last['id']}/"})
    low_margin = [p for p in profitability if 0 < p['margin_pct'] < 15][:5]
    if low_margin:
        actions.append({'sev': 'medium', 'icon': 'fa-percent',
            'title': f"Catégories à faible marge (<15%) : {', '.join(p['category'] for p in low_margin)}",
            'detail': "Revoir le prix de vente ou le coût d'achat.", 'link': '/sales/insights/'})

    return {
        'overview': overview,
        'categories': categories,
        'weight_ranges': weight_ranges,
        'top_clients': top_clients,
        'client_stats': client_stats,
        'stock_aging': stock_aging,
        'sell_through': sell_through,
        'delivery': delivery_data,
        'daily_trend': daily_trend,
        'data_quality': data_quality,
        'profitability': profitability,
        'day_of_week': day_of_week,
        'cat_client_type': cat_client_type,
        'co_purchase': top_co_purchases,
        'repeat_cat_pref': repeat_cat_pref,
        'price_distribution': price_distribution,
        'weekly_trend': weekly_trend,
        # Operational / decision modules
        'circulation': circulation,
        'deposits': deposits_mod,
        'sellers': sellers,
        'inventory_health': inventory_health,
        'aged_stock': aged_stock,
        'profit_totals': profit_totals,
        'receivables': receivables,
        'actions': actions,
    }


def build_ai_prompt(data):
    """
    Build a structured prompt with computed data for the AI business advisor.
    Focus on cross-correlations and non-obvious patterns.
    """
    ov = data['overview']

    # Format categories table
    cat_lines = []
    for c in data['categories'][:12]:
        cat_lines.append(
            f"  - {c['name']}: {c['items_sold']} vendus, {c['revenue']} DH, "
            f"prix moy {c['avg_price']} DH, poids moy {c['avg_weight_g']}g, "
            f"{c['pct_revenue']}% du CA"
        )

    # Format weight ranges
    wr_lines = []
    for wr in data['weight_ranges']:
        ranges_detail = ', '.join(
            f"{k}: {v['count']} pcs ({v['revenue']} DH)"
            for k, v in wr['all_ranges'].items()
        )
        wr_lines.append(f"  - {wr['category']}: meilleure gamme = {wr['best_range']} ({wr['best_range_count']} pcs, {wr['best_range_revenue']} DH). Détail: {ranges_detail}")

    # Format sell-through
    st_lines = []
    for s in data['sell_through']:
        st_lines.append(f"  - {s['category']}: {s['sell_through_pct']}% vendu ({s['sold']} vendus, {s['available']} en stock)")

    # Format client stats
    cs = data['client_stats']
    freq = cs['frequency']

    # Format profitability
    prof_lines = []
    for p in data['profitability']:
        prof_lines.append(
            f"  - {p['category']}: {p['items']} articles, coût {p['total_cost']} DH, "
            f"vente {p['total_revenue']} DH, marge {p['margin']} DH ({p['margin_pct']}%)"
        )

    # Format delivery
    del_lines = []
    for d in data['delivery']:
        del_lines.append(
            f"  - {d['delivery_method_type']}: {d['count']} factures, {d['revenue']} DH, "
            f"{d['with_client']} avec client, {d['anonymous']} anonymes"
        )

    # Format stock aging
    sa = data['stock_aging']
    stock_cat_lines = []
    for sc in sa['by_category'][:10]:
        stock_cat_lines.append(f"  - {sc['category__name']}: {sc['count']} en stock")

    # Data quality
    dq = data['data_quality']

    # NEW: Day-of-week patterns
    dow_lines = []
    for d in data.get('day_of_week', []):
        dow_lines.append(f"  - {d['day']}: {d['count']} ventes, {d['revenue']} DH, panier moy {d['avg_basket']} DH")

    # NEW: Category x client type
    cat_client_lines = []
    for c in data.get('cat_client_type', []):
        total = float(c['total_rev'] or 1)
        anon_pct = round(float(c['anon_rev'] or 0) * 100 / total, 1)
        cat_client_lines.append(
            f"  - {c['product__category__name']}: {anon_pct}% anonyme "
            f"(client: {c['client_count']} pcs/{c['client_rev'] or 0} DH, "
            f"anonyme: {c['anon_count']} pcs/{c['anon_rev'] or 0} DH)"
        )

    # NEW: Co-purchase patterns
    co_lines = []
    for pair, count in data.get('co_purchase', []):
        co_lines.append(f"  - {pair[0]} + {pair[1]}: {count} fois achetés ensemble")

    # NEW: Repeat client preferences
    repeat_lines = []
    for r in data.get('repeat_cat_pref', []):
        repeat_lines.append(f"  - {r['product__category__name']}: {r['count']} articles, {_d(r['revenue'])} DH")

    # NEW: Price distribution
    price_lines = []
    for p in data.get('price_distribution', []):
        price_lines.append(
            f"  - {p['category']}: min {p['min']:.0f}, P25 {p['p25']:.0f}, "
            f"médiane {p['median']:.0f}, P75 {p['p75']:.0f}, max {p['max']:.0f} DH ({p['count']} ventes)"
        )

    # NEW: Weekly trend
    week_lines = []
    for w in data.get('weekly_trend', []):
        week_lines.append(f"  - Sem {w['week'].strftime('%d/%m')}: {w['count']} factures, {_d(w['revenue'])} DH, panier {_d(w['avg_basket'])} DH")

    # NEW: operational modules (circulation, dépôts, vendeuses, inventaire, décisions)
    circ = data.get('circulation', {})
    dep = data.get('deposits', {})
    invh = data.get('inventory_health', {})
    aged = data.get('aged_stock', {})
    pt = data.get('profit_totals', {})
    seller_lines = [
        f"  - {s['name']}: {s['revenue']} DH, {s['invoices']} factures, {s['circ_sold']} ventes en circulation"
        for s in data.get('sellers', [])[:10]
    ]
    circ_seller_lines = [f"  - {r['name']}: {r['out']} en circulation" for r in circ.get('by_seller', [])]
    dep_seller_lines = [f"  - {r['name']}: {r['balance']} DH ({r['accounts']} comptes)" for r in dep.get('by_seller', [])]
    action_lines = [f"  - [{a['sev']}] {a['title']} — {a['detail']}" for a in data.get('actions', [])]
    _il = invh.get('last_session')
    inv_line = (
        f"Dernier contrôle #{_il['id']} ({_il['mode']}, {_il['date']}): attendus {_il['expected']}, "
        f"scannés {_il['scanned']}, manquants {_il['missing']}, anomalies {_il['anomalies']}"
        if _il else "Aucun contrôle d'inventaire terminé"
    )
    aged180 = aged.get('over_180d', {})
    aged365 = aged.get('over_365d', {})

    # NEW: decision intelligence (buy/stop, win-back, cash to unlock)
    di = data.get('decision_intel', {})
    di_growth = di.get('growth', {})
    reorder_lines = [f"  - {r['cat']}: écoulement {r['sell_through']}%, il reste {r['in_stock']} en stock ({r['sold']} vendus)" for r in di.get('reorder', [])]
    liquidate_lines = [f"  - {r['cat']}: écoulement {r['sell_through']}%, {r['in_stock']} en stock, {r['capital']} DH de capital immobilisé" for r in di.get('liquidate', [])]
    prof_eff_lines = [f"  - {p['cat']}: marge {p['margin']} DH ({p['margin_pct']}%), {p['margin_per_gram']} DH/g" for p in di.get('profit_efficiency', [])]
    winback_lines = [f"  - {w['name']} ({w['phone']}): {w['spend']} DH dépensés, {w['orders']} achats, silencieux depuis {w['days']}j" for w in di.get('win_back', [])]
    di_cash = di.get('cash_to_unlock', {})

    prompt = f"""Tu es un expert-conseil en bijouterie or au Maroc avec 20 ans d'expérience dans le secteur.
Tu connais parfaitement :
- Le marché marocain de l'or : cours de l'or, impact du prix du gramme sur les marges, différence entre or 18k et 9k
- La culture d'achat bijouterie au Maroc : trousseau de mariage (jihaz), dot (sadaq), cadeaux de fêtes (Eid, Mouloud), saison des moussems, achats Ramadan
- Les spécificités produit : Sertla = pièce maîtresse du trousseau marocain, Demlij = tradition de mariage, Mcherta = bijou festif, importance du poids en or vs le travail artisanal (siyagha)
- La saisonnalité : pic avant Ramadan, mariages en été (juin-septembre), Eid al-Adha, rentrée scolaire (baisse), période creuse janvier-février
- Le comportement client marocain : achat cash fréquent (d'où les anonymes), négociation sur le prix du gramme, achat familial (mère + fille), revente/échange d'ancien or contre du neuf
- La gestion de trésorerie bijouterie : l'or est un actif qui ne perd pas de valeur, le stock n'est pas un coût mort comme en retail classique, importance du ratio cash/stock

Je suis le propriétaire de cette bijouterie. Je connais DÉJÀ les bases (mes top catégories, que j'ai beaucoup d'anonymes, etc).

Ce que je veux de toi : des INSIGHTS CACHÉS spécifiques au MÉTIER DE BIJOUTIER, des CORRÉLATIONS NON-ÉVIDENTES, des ANOMALIES dans mes données.
NE ME DIS PAS ce que je sais déjà. NE DONNE PAS de conseils génériques de retail.
Chaque recommandation doit être contextualisée au marché marocain de la bijouterie or.

=== VUE D'ENSEMBLE ===
Période: {ov['date_first']} → {ov['date_last']}
CA: {ov['total_revenue']} DH | {ov['total_invoices']} factures | Panier moyen: {ov['avg_basket']} DH
Client identifié: {ov['with_client']} ({100 - ov['anonymous_pct']}%) → {ov['revenue_client']} DH
Anonyme: {ov['without_client']} ({ov['anonymous_pct']}%) → {ov['revenue_anonymous']} DH

=== CATÉGORIES (par CA) ===
{chr(10).join(cat_lines)}

=== GAMMES DE POIDS ===
{chr(10).join(wr_lines)}

=== TAUX D'ÉCOULEMENT ===
{chr(10).join(st_lines)}

=== RENTABILITÉ (produits avec coût connu) ===
{chr(10).join(prof_lines) if prof_lines else "  Données insuffisantes"}

=== DISTRIBUTION DES PRIX PAR CATÉGORIE ===
{chr(10).join(price_lines)}

=== PATTERN JOUR DE SEMAINE ===
{chr(10).join(dow_lines)}

=== TENDANCE HEBDOMADAIRE ===
{chr(10).join(week_lines)}

=== CATÉGORIE × TYPE CLIENT (anonyme vs identifié) ===
{chr(10).join(cat_client_lines)}

=== COMBINAISONS D'ACHAT (catégories achetées ensemble) ===
{chr(10).join(co_lines) if co_lines else "  Peu de factures multi-catégories"}

=== CE QUE LES CLIENTS FIDÈLES ACHÈTENT (2+ achats) ===
{chr(10).join(repeat_lines) if repeat_lines else "  Peu de clients récurrents"}

=== CLIENTS ===
{cs['total_unique']} clients identifiés: {freq['1_time']} one-shot ({cs['one_time_pct']}%), {freq['2_times']} x2, {freq['3_plus']} x3+

=== CANAUX DE LIVRAISON ===
{chr(10).join(del_lines)}

=== STOCK ===
Total: {sa['total_available']} | 0-30j: {sa['0_30d']} | 31-60j: {sa['31_60d']} | 60j+: {sa['60d_plus']}
{chr(10).join(stock_cat_lines)}

=== QUALITÉ DONNÉES ===
{dq['zero_purchase_price']}/{dq['total_sold']} ({dq['zero_price_pct']}%) sans prix d'achat

=== RENTABILITÉ GLOBALE ===
Coût {pt.get('total_cost')} DH → Vente {pt.get('total_revenue')} DH | Marge {pt.get('total_margin')} DH ({pt.get('margin_pct')}%)
Créances (impayés): {data.get('receivables')} DH

=== STOCK ÂGÉ (capital immobilisé) ===
>180j: {aged180.get('count')} pièces / {aged180.get('value')} DH
>365j: {aged365.get('count')} pièces / {aged365.get('value')} DH

=== CIRCULATION (vente en ligne / vendeuses) ===
En circulation: {circ.get('out_count')} | Vendues: {circ.get('sold_count')} | Retours: {circ.get('returned_count')} | Conversion: {circ.get('conversion_pct')}%
Dormantes (sorties >30j): {circ.get('out_over_30d')}
{chr(10).join(circ_seller_lines) if circ_seller_lines else "  Aucune en circulation"}

=== DÉPÔTS CLIENTS (avances détenues) ===
Total détenu: {dep.get('total_held')} DH sur {dep.get('account_count')} comptes
{chr(10).join(dep_seller_lines) if dep_seller_lines else "  Aucun dépôt"}

=== PERFORMANCE VENDEUSES ===
{chr(10).join(seller_lines) if seller_lines else "  Vendeuse non renseignée sur les factures"}

=== SANTÉ INVENTAIRE (blocs & contrôle) ===
Blocs actifs: {invh.get('blocks_count')} | Produits disponibles: {invh.get('available_total')}
{inv_line}

=== DÉCISIONS DÉTECTÉES (à prioriser et développer) ===
{chr(10).join(action_lines) if action_lines else "  Aucune alerte automatique"}

=== MOMENTUM (30 derniers jours vs 30 précédents) ===
CA: {di_growth.get('cur_rev')} DH ({di_growth.get('cur_n')} factures) vs {di_growth.get('prev_rev')} DH → {di_growth.get('growth_pct')}%

=== À RÉAPPROVISIONNER (fort écoulement, stock bas) ===
{chr(10).join(reorder_lines) if reorder_lines else "  Rien d'urgent"}

=== À LIQUIDER / ARRÊTER D'ACHETER (faible écoulement, capital bloqué) ===
{chr(10).join(liquidate_lines) if liquidate_lines else "  Aucune catégorie évidente"}

=== RENTABILITÉ RÉELLE (marge par catégorie et par gramme) ===
{chr(10).join(prof_eff_lines) if prof_eff_lines else "  Coûts d'achat insuffisants"}

=== TRÉSORERIE À DÉBLOQUER ===
Total mobilisable {di_cash.get('total')} DH = créances {di_cash.get('receivables')} + stock mort {di_cash.get('dead_capital')} + circulation {di_cash.get('circulation_value')}

=== CLIENTS À RÉACTIVER (bons clients silencieux >90j) ===
{chr(10).join(winback_lines) if winback_lines else "  Aucun"}

=== CE QUE J'ATTENDS DE TOI ===

Réponds en 5 sections. Pour chaque section, je veux:
- Des DÉCOUVERTES que je ne peux PAS voir juste en regardant un tableau
- Des CORRÉLATIONS entre les différentes données ci-dessus
- Des chiffres PRÉCIS tirés des données
- Un raisonnement MÉTIER BIJOUTERIE (pas du retail générique)

## 1. OPPORTUNITÉS CACHÉES (Spécifique Bijouterie)
- Croise écoulement + stock + marge : quelles pièces sont en rupture imminente sur des articles à forte demande (trousseau, mariage)?
- Quelles combinaisons d'achat révèlent un comportement "trousseau" (Sertla + Demlij + Ensemble = probable mariage)?
- Y a-t-il un décalage entre le poids moyen vendu et le poids moyen en stock (tu stockes du lourd mais vends du léger, ou l'inverse)?
- Compare le CA/gramme entre catégories : où la valeur ajoutée artisanale (siyagha) est-elle la mieux valorisée?
- Bundle naturels à proposer basés sur les co-achats ET les traditions marocaines

## 2. ANOMALIES & SIGNAUX D'ALERTE (Contexte Or Maroc)
- Catégories avec taux d'écoulement anormalement bas : est-ce un problème de design dépassé, de prix trop élevé vs cours de l'or, ou de stock mal calibré en poids?
- Le panier moyen varie-t-il selon les jours de manière cohérente avec le calendrier marocain (vendredi = jour de souk/marché)?
- Catégories où le prix médian ≠ prix moyen : signe de pièces invendables qui tirent la moyenne (or ancien/modèle démodé)?
- Attention aux articles en stock >60 jours : en bijouterie, ce n'est PAS forcément un problème (l'or garde sa valeur), MAIS le coût d'opportunité de ce capital immobilisé doit être évalué vs le cours actuel de l'or

## 3. STRATÉGIE PRIX & MARGE (Réalité Bijoutier)
- Analyse le ratio marge/poids : certaines catégories ont-elles une siyagha (valeur artisanale) sous-évaluée?
- Compare le prix de vente au gramme entre catégories : lesquelles valorisent le mieux le travail du bijoutier vs simple poids d'or?
- Les "trous" dans la gamme de prix : manque-t-il des pièces accessibles (premier achat or, cadeau Eid) ou des pièces premium (mariage haut de gamme)?
- Les clients fidèles achètent-ils les mêmes catégories (besoin récurrent = cadeaux) ou diversifient-ils (trousseau progressif)?

## 4. CLIENTÈLE & SAISONNALITÉ MAROCAINE
- Comportement d'achat anonyme : au Maroc c'est culturel (cash, discrétion), ne PAS considérer comme un problème à résoudre. Mais identifier les leviers naturels de captation (livraison, SAV, échange)
- Quel canal convertit le mieux? Le transporteur force l'identification — propose un service de livraison pour les achats trousseau
- Anticipe la prochaine saison : basé sur les tendances, qu'est-ce qui va se vendre dans les 2-4 prochaines semaines? (Ramadan? Eid? Saison mariages?)
- Profil des meilleurs clients : acheteurs one-shot à gros panier (trousseau) vs clients réguliers à petit panier (cadeaux) — lesquels sont les plus rentables?

## 5. PLAN D'ACHAT & STOCK (Décisions Bijoutier)
En croisant écoulement + marge + stock + saisonnalité marocaine à venir:
- Quelles pièces SPÉCIFIQUES commander cette semaine et en quelle quantité?
- Stock à écouler en priorité (promotion, fonte/transformation, échange?)
- Où investir le prochain dirham en tenant compte du cours de l'or actuel?
- Faut-il privilégier des pièces légères (accessibles, rotation rapide) ou lourdes (marge en DH, trousseau)?
- Mini plan d'achat chiffré avec budget estimé

## 6. PLAN D'ACTION PRIORISÉ (Décisions cette semaine)
En te basant sur les DÉCISIONS DÉTECTÉES, la CIRCULATION, les DÉPÔTS, les CRÉANCES, le STOCK ÂGÉ et la SANTÉ INVENTAIRE:
- Classe 3 à 6 actions concrètes par ORDRE DE PRIORITÉ (impact DH × urgence), chacune avec le chiffre exact et le geste précis.
- Circulation dormante: quelles vendeuses relancer et pour combien de pièces/valeur?
- Stock âgé: quelles catégories brader/transformer en priorité (croise avec le taux d'écoulement)?
- Écarts d'inventaire: si des manquants, estimer le risque de démarque vs erreur de statut.
- Créances & dépôts: trésorerie à récupérer vs engagements à honorer.
- Termine par UNE décision n°1 à exécuter aujourd'hui.

RAPPEL: Tu es un EXPERT BIJOUTIER MAROCAIN, pas un consultant retail générique.
PAS DE CONSEILS GÉNÉRIQUES (type "améliorez votre marketing digital" ou "fidélisez vos clients").
Si tu ne peux pas le prouver avec un chiffre des données ci-dessus, ne le dis pas."""

    return prompt


def generate_ai_insights(data):
    """
    Send computed data to AI for business interpretation.
    Returns the AI response as structured text.
    """
    from ai_services.scaleway_client import chat_completion, MODELS, is_configured

    if not is_configured():
        return None

    prompt = build_ai_prompt(data)

    try:
        response = chat_completion(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=MODELS['chat_reasoning'],
            temperature=0.4,
            max_tokens=8192,
        )
        return response
    except Exception as e:
        logger.error(f'AI insights generation failed: {e}')
        return None
