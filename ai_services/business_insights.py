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
