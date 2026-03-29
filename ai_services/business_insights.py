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

    # ===== 11. PROFITABILITY (products with known costs) =====
    profitable_items = items_qs.filter(
        product__purchase_price_per_gram__gt=0,
        product__net_weight__gt=0,
    ).values(
        'product__category__name',
    ).annotate(
        items=Count('id'),
        total_cost=Sum(F('product__net_weight') * F('product__purchase_price_per_gram')),
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
    }


def build_ai_prompt(data):
    """
    Build a structured prompt with computed data for the AI business advisor.
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

    prompt = f"""Tu es un conseiller business expert en bijouterie marocaine (or 18 carats principalement).
Analyse les données réelles suivantes et donne des recommandations SPÉCIFIQUES, CHIFFRÉES et ACTIONNABLES.

=== DONNÉES DE VENTE ===
Période: {ov['date_first']} → {ov['date_last']}
CA total: {ov['total_revenue']} DH sur {ov['total_invoices']} factures
Panier moyen: {ov['avg_basket']} DH

Ventes avec client identifié: {ov['with_client']} ({100 - ov['anonymous_pct']}%) → {ov['revenue_client']} DH
Ventes anonymes: {ov['without_client']} ({ov['anonymous_pct']}%) → {ov['revenue_anonymous']} DH

=== CATÉGORIES (classées par CA) ===
{chr(10).join(cat_lines)}

=== GAMMES DE POIDS PAR CATÉGORIE ===
{chr(10).join(wr_lines)}

=== TAUX D'ÉCOULEMENT (sell-through) ===
{chr(10).join(st_lines)}

=== RENTABILITÉ PAR CATÉGORIE (produits avec coût connu) ===
{chr(10).join(prof_lines) if prof_lines else "  Données insuffisantes - beaucoup de produits sans prix d'achat"}

=== CLIENTS ===
{cs['total_unique']} clients identifiés
- {freq['1_time']} achètent 1 seule fois ({cs['one_time_pct']}%)
- {freq['2_times']} achètent 2 fois
- {freq['3_plus']} achètent 3 fois ou plus

=== CANAUX DE LIVRAISON ===
{chr(10).join(del_lines)}

=== STOCK DISPONIBLE ===
Total en stock: {sa['total_available']} articles
- 0-30 jours: {sa['0_30d']} | 31-60 jours: {sa['31_60d']} | 60+ jours: {sa['60d_plus']}
Par catégorie:
{chr(10).join(stock_cat_lines)}

=== QUALITÉ DES DONNÉES ===
{dq['zero_purchase_price']}/{dq['total_sold']} produits vendus ({dq['zero_price_pct']}%) ont un prix d'achat à 0 DH (création rapide)

=== DONNE TES RECOMMANDATIONS EN 5 SECTIONS ===

**1. INVESTISSEMENT PRODUITS**
Quelles catégories acheter en priorité? Quelles gammes de poids privilégier? Combien investir proportionnellement? Base-toi sur le CA, le taux d'écoulement et le panier moyen.

**2. STRATÉGIE MARKETING**
Quels produits mettre en avant? Comment convertir les {ov['anonymous_pct']}% de ventes anonymes en clients identifiés? Quels canaux de livraison exploiter davantage?

**3. POLITIQUE DE PRIX**
Analyse des marges par catégorie (quand les données sont disponibles). Les prix sont-ils cohérents? Y a-t-il des catégories sous-évaluées ou sur-évaluées?

**4. FIDÉLISATION CLIENT**
{cs['one_time_pct']}% des clients n'achètent qu'une fois. Comment les faire revenir? Stratégies concrètes adaptées à une bijouterie marocaine.

**5. ALERTES & ACTIONS IMMÉDIATES**
Problèmes détectés, actions urgentes à prendre (qualité des données, stock qui ne bouge pas, etc.)

Sois CONCRET avec des chiffres. Pas de généralités. Chaque recommandation doit être actionnable CETTE SEMAINE."""

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
            max_tokens=4096,
        )
        return response
    except Exception as e:
        logger.error(f'AI insights generation failed: {e}')
        return None
