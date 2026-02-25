"""
AI-powered query handler for Bijouterie Hafsa ERP.
Supports French, Arabic (MSA), and Moroccan Darija.
Used by Telegram bot AND web admin chat.
"""

import json
import logging
from decimal import Decimal
from datetime import timedelta
from django.db.models import Q, Sum, Count
from django.utils import timezone

from . import scaleway_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'assistant IA de Bijouterie Hafsa, une bijouterie au Maroc. Tu aides le personnel du magasin à trouver des informations rapidement.

Tu comprends le français, l'arabe standard, et le darija marocain. Exemples en darija:
- "chhal dkhel lyoum?" = "combien on a encaissé aujourd'hui?" → get_dashboard_summary(today)
- "chhal dkhel lbareh?" = "combien on a encaissé hier?" → get_dashboard_summary(yesterday)
- "chhal men khtem d dehab?" = "combien de bagues en or?" → count_products
- "3tini solde dyal client Ahmed" = "donne-moi le solde du client Ahmed" → get_client_info
- "wach kayn chi bracelet d 18K?" = "est-ce qu'il y a des bracelets en 18K?" → search_products
- "chno les ventes dyal lyoum?" = "quelles sont les ventes d'aujourd'hui?" → get_sales_stats(today)
- "chkoun li ba3 kter had chher?" = "qui a le plus vendu ce mois?" → get_seller_performance(month)
- "wach waslet la livraison dyal LIV-XXX?" → get_delivery_status
- "feen waslet la commande dyal Fatima?" → search_delivery
- "chkoun huma top client dyalna?" = "qui sont nos meilleurs clients?" → get_top_clients(month)
- "chno li tba3 kter?" = "qu'est-ce qui se vend le plus?" → get_top_products(month)

IMPORTANT: Tu as accès à TOUTES les données du système. Tu dois TOUJOURS appeler une fonction pour répondre — ne dis JAMAIS "je n'ai pas accès" ou "je ne peux pas". Si la question concerne des données, appelle la fonction la plus proche.

GUIDE DE ROUTAGE:
- "dkhel/encaissé/résumé/tableau de bord" → get_dashboard_summary (PAS get_sales_stats)
- "ventes/CA/chiffre d'affaires" → get_sales_stats
- "top/meilleur/fidèle clients" → get_top_clients
- "top/meilleur produits/best seller" → get_top_products
- "vendeur/performance/qui a vendu" → get_seller_performance
- "livraison/LIV-/suivi/tracking" → get_delivery_status
- "en attente/pending" → get_pending_deliveries
- "paiement/espèces/virement/chèque" → get_payment_breakdown
- "stock/inventaire" → get_inventory_summary
- "achat/fournisseur" → get_purchase_stats
- "réparation" → get_repair_stats

Pour répondre, retourne UNIQUEMENT un JSON avec la fonction à appeler:

FONCTIONS DISPONIBLES:

1. search_products: Chercher des produits par nom, référence, catégorie, description
   {"function": "search_products", "params": {"query": "texte", "status": "available"}}

2. count_products: Compter des produits avec filtres
   {"function": "count_products", "params": {"metal_type": "or", "purity": "18K", "category": "bague", "status": "available"}}

3. get_client_info: Info client (solde dépôt, téléphone, code)
   {"function": "get_client_info", "params": {"name": "nom du client"}}

4. get_client_sales: Historique des ventes d'un client
   {"function": "get_client_sales", "params": {"name": "nom du client", "limit": 10}}

5. get_sales_stats: Statistiques de ventes (CA, factures, poids, remises)
   {"function": "get_sales_stats", "params": {"period": "today/yesterday/week/last_week/month/last_month/year"}}

6. get_product_by_ref: Détail d'un produit par référence exacte
   {"function": "get_product_by_ref", "params": {"reference": "REF-XXX"}}

7. get_invoice_detail: Détail d'une facture de vente par référence
   {"function": "get_invoice_detail", "params": {"reference": "INV-XXXXXXXX-XXXX"}}

8. get_delivery_status: Statut d'une livraison par référence ou numéro de suivi
   {"function": "get_delivery_status", "params": {"reference": "LIV-XXXXXXXX-XXXX"}}

9. get_dashboard_summary: Résumé complet (CA, encaissé réel, livraisons, paiements, dépôts). Utilise cette fonction pour "chhal dkhel" et toute question sur l'encaissement.
   {"function": "get_dashboard_summary", "params": {"period": "today/yesterday/week/last_week/month/last_month/year"}}

10. get_payment_breakdown: Détail paiements par méthode (espèces, virement, chèque) et par banque
    {"function": "get_payment_breakdown", "params": {"period": "today/yesterday/week/month"}}

11. get_delivery_stats: Stats livraisons par type (magasin, AMANA, transporteur, en stock)
    {"function": "get_delivery_stats", "params": {"period": "today/yesterday/week/month"}}

12. get_seller_performance: Performance des vendeurs (CA, factures, poids par vendeur)
    {"function": "get_seller_performance", "params": {"period": "today/yesterday/week/last_week/month"}}

13. get_pending_deliveries: Livraisons en attente (AMANA + transporteur non livrées)
    {"function": "get_pending_deliveries", "params": {}}

14. get_purchase_stats: Statistiques achats fournisseurs
    {"function": "get_purchase_stats", "params": {"period": "today/month"}}

15. get_inventory_summary: Résumé du stock (total produits, valeur, par catégorie/métal)
    {"function": "get_inventory_summary", "params": {}}

16. search_delivery: Chercher une livraison par nom client ou tracking
    {"function": "search_delivery", "params": {"query": "nom client ou tracking"}}

17. get_repair_stats: Statistiques des réparations
    {"function": "get_repair_stats", "params": {"period": "today/month"}}

18. get_top_clients: Meilleurs clients par CA, nombre d'achats et poids
    {"function": "get_top_clients", "params": {"period": "month", "limit": 10}}

19. get_top_products: Produits les plus vendus par quantité et CA
    {"function": "get_top_products", "params": {"period": "month", "limit": 10}}

20. general_answer: UNIQUEMENT pour les salutations et questions sans rapport avec les données
    {"function": "general_answer", "params": {"answer": "ta réponse ici"}}

PERIODES SUPPORTEES: today (aujourd'hui), yesterday (hier), week (cette semaine), last_week (semaine dernière), month (ce mois), last_month (mois dernier), year (cette année)

Retourne UNIQUEMENT le JSON, rien d'autre.
"""


def process_ai_query(text):
    """
    Process a natural language query and return a response.

    Args:
        text: User's message text (French, Arabic, or Darija)

    Returns:
        str: Response text to send back to the user
    """
    if not scaleway_client.is_configured():
        return "Service IA non configuré. Contactez l'administrateur."

    try:
        messages = [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': text},
        ]

        response = scaleway_client.chat_completion(
            messages=messages,
            model=scaleway_client.MODELS['chat'],
            temperature=0.1,
            max_tokens=512,
        )

        clean = response.strip()
        if clean.startswith('```'):
            lines = clean.split('\n')
            clean = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        function_call = json.loads(clean)
        func_name = function_call.get('function', 'general_answer')
        params = function_call.get('params', {})

        result = _execute_function(func_name, params)

        if func_name == 'general_answer':
            return params.get('answer', result)

        # 2nd AI pass: format data into natural response
        return _ai_format_response(func_name, result, text)

    except json.JSONDecodeError:
        return response if response else "Désolé, je n'ai pas compris. Essayez de reformuler."
    except Exception as e:
        logger.error(f'AI query error: {e}')
        return f"Erreur: {str(e)}"


def _execute_function(func_name, params):
    """Execute a database function based on AI's decision."""
    handlers = {
        'search_products': _fn_search_products,
        'count_products': _fn_count_products,
        'get_client_info': _fn_get_client_info,
        'get_client_sales': _fn_get_client_sales,
        'get_sales_stats': _fn_get_sales_stats,
        'get_product_by_ref': _fn_get_product_by_ref,
        'get_invoice_detail': _fn_get_invoice_detail,
        'get_delivery_status': _fn_get_delivery_status,
        'get_dashboard_summary': _fn_get_dashboard_summary,
        'get_payment_breakdown': _fn_get_payment_breakdown,
        'get_delivery_stats': _fn_get_delivery_stats,
        'get_seller_performance': _fn_get_seller_performance,
        'get_pending_deliveries': _fn_get_pending_deliveries,
        'get_purchase_stats': _fn_get_purchase_stats,
        'get_inventory_summary': _fn_get_inventory_summary,
        'search_delivery': _fn_search_delivery,
        'get_repair_stats': _fn_get_repair_stats,
        'get_top_clients': _fn_get_top_clients,
        'get_top_products': _fn_get_top_products,
        'general_answer': lambda p: p.get('answer', ''),
    }

    try:
        handler = handlers.get(func_name)
        if handler:
            return handler(params)
        return {'error': f'Fonction inconnue: {func_name}'}
    except Exception as e:
        logger.error(f'Function execution error ({func_name}): {e}')
        return {'error': str(e)}


# ============ DATE RANGE HELPER ============

def _get_date_range(period):
    """Return (start_date, end_date, label) for a period string."""
    today = timezone.now().date()

    if period == 'today':
        return today, today, "Aujourd'hui"
    elif period == 'yesterday':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday, "Hier"
    elif period == 'week':
        week_start = today - timedelta(days=today.weekday())
        return week_start, today, "Cette semaine"
    elif period == 'last_week':
        last_week_end = today - timedelta(days=today.weekday() + 1)
        last_week_start = last_week_end - timedelta(days=6)
        return last_week_start, last_week_end, "Semaine dernière"
    elif period == 'month':
        return today.replace(day=1), today, "Ce mois"
    elif period == 'last_month':
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end, "Mois dernier"
    elif period == 'year':
        return today.replace(month=1, day=1), today, "Cette année"
    else:
        return today.replace(day=1), today, "Ce mois"


# ============ PRODUCT FUNCTIONS ============

def _fn_search_products(params):
    from products.models import Product
    query = params.get('query', '')
    status = params.get('status', 'available')

    qs = Product.objects.select_related('category', 'metal_type', 'metal_purity')
    if status:
        qs = qs.filter(status=status)
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(name_ar__icontains=query) |
            Q(reference__icontains=query) | Q(category__name__icontains=query) |
            Q(description__icontains=query) | Q(barcode__icontains=query)
        )

    products = qs[:10]
    return [{
        'reference': p.reference,
        'name': p.name,
        'category': p.category.name if p.category else '-',
        'metal': f"{p.metal_type.name if p.metal_type else ''} {p.metal_purity.name if p.metal_purity else ''}".strip(),
        'weight': str(p.gross_weight or 0) + 'g',
        'price': str(p.selling_price or 0) + ' DH',
        'status': p.get_status_display(),
    } for p in products]


def _fn_count_products(params):
    from products.models import Product
    qs = Product.objects.all()
    status = params.get('status', 'available')
    if status:
        qs = qs.filter(status=status)
    if params.get('metal_type'):
        qs = qs.filter(metal_type__name__icontains=params['metal_type'])
    if params.get('purity'):
        qs = qs.filter(metal_purity__name__icontains=params['purity'])
    if params.get('category'):
        qs = qs.filter(category__name__icontains=params['category'])

    count = qs.count()
    total_weight = qs.aggregate(w=Sum('gross_weight'))['w'] or 0
    total_value = qs.aggregate(v=Sum('selling_price'))['v'] or 0

    return {
        'count': count,
        'total_weight': f'{total_weight}g',
        'total_value': f'{total_value} DH',
    }


def _fn_get_product_by_ref(params):
    from products.models import Product
    ref = params.get('reference', '')
    if not ref:
        return {'error': 'Référence requise'}
    try:
        p = Product.objects.select_related('category', 'metal_type', 'metal_purity', 'supplier').get(reference__iexact=ref)
        return {
            'reference': p.reference, 'name': p.name,
            'category': p.category.name if p.category else '-',
            'metal': f"{p.metal_type.name if p.metal_type else ''} {p.metal_purity.name if p.metal_purity else ''}".strip(),
            'weight': f"{p.gross_weight or 0}g",
            'selling_price': f"{p.selling_price or 0} DH",
            'cost': f"{p.total_cost or 0} DH",
            'status': p.get_status_display(),
            'supplier': p.supplier.name if p.supplier else '-',
            'location': p.location or '-',
        }
    except Product.DoesNotExist:
        return {'error': f'Produit {ref} introuvable'}


def _fn_get_inventory_summary(params):
    from products.models import Product
    qs = Product.objects.filter(status='available')

    total = qs.aggregate(
        count=Count('id'), weight=Sum('gross_weight'),
        value=Sum('selling_price'), cost=Sum('total_cost'),
    )

    by_category = list(qs.values('category__name').annotate(
        count=Count('id'), weight=Sum('gross_weight'), value=Sum('selling_price'),
    ).order_by('-value')[:10])

    by_metal = list(qs.values('metal_type__name').annotate(
        count=Count('id'), weight=Sum('gross_weight'), value=Sum('selling_price'),
    ).order_by('-value')[:10])

    return {
        'total_products': total['count'] or 0,
        'total_weight': f"{total['weight'] or 0}g",
        'total_value': f"{total['value'] or 0} DH",
        'total_cost': f"{total['cost'] or 0} DH",
        'by_category': [{
            'name': c['category__name'] or 'Sans catégorie',
            'count': c['count'], 'weight': f"{c['weight'] or 0}g", 'value': f"{c['value'] or 0} DH",
        } for c in by_category],
        'by_metal': [{
            'name': m['metal_type__name'] or 'Sans métal',
            'count': m['count'], 'weight': f"{m['weight'] or 0}g", 'value': f"{m['value'] or 0} DH",
        } for m in by_metal],
    }


# ============ CLIENT FUNCTIONS ============

def _fn_get_client_info(params):
    from clients.models import Client
    from deposits.models import DepositAccount
    name = params.get('name', '')
    if not name:
        return {'error': 'Nom du client requis'}

    clients = Client.objects.filter(
        Q(first_name__icontains=name) | Q(last_name__icontains=name) | Q(phone__icontains=name)
    )[:5]

    results = []
    for c in clients:
        info = {'name': c.full_name, 'phone': c.phone or '-', 'code': c.code}
        try:
            deposit = DepositAccount.objects.get(client=c)
            info['deposit_balance'] = f'{deposit.balance} DH'
        except DepositAccount.DoesNotExist:
            info['deposit_balance'] = 'Pas de compte dépôt'
        results.append(info)
    return results


def _fn_get_client_sales(params):
    from clients.models import Client
    from sales.models import SaleInvoice
    name = params.get('name', '')
    limit = params.get('limit', 10)
    if not name:
        return {'error': 'Nom du client requis'}

    clients = Client.objects.filter(
        Q(first_name__icontains=name) | Q(last_name__icontains=name) | Q(phone__icontains=name)
    )[:3]

    results = []
    for c in clients:
        invoices = SaleInvoice.objects.filter(
            client=c, is_deleted=False
        ).exclude(status='returned').order_by('-date')[:limit]

        total = invoices.aggregate(total=Sum('total_amount'), paid=Sum('amount_paid'))

        results.append({
            'client': c.full_name,
            'total_invoices': invoices.count(),
            'total_amount': f"{total['total'] or 0} DH",
            'total_paid': f"{total['paid'] or 0} DH",
            'invoices': [{
                'ref': inv.reference,
                'date': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
                'amount': f"{inv.total_amount or 0} DH",
                'status': inv.get_status_display(),
                'paid': f"{inv.amount_paid or 0} DH",
            } for inv in invoices],
        })
    return results


# ============ TOP CLIENTS / TOP PRODUCTS ============

def _fn_get_top_clients(params):
    from sales.models import SaleInvoice
    period = params.get('period', 'month')
    limit = params.get('limit', 10)
    start_date, end_date, label = _get_date_range(period)

    base = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date,
        client__isnull=False,
    ).exclude(status='returned')

    clients = list(base.values(
        'client__first_name', 'client__last_name', 'client__phone',
    ).annotate(
        count=Count('id'), revenue=Sum('total_amount'),
        paid=Sum('amount_paid'), weight=Sum('items__product__gross_weight'),
    ).order_by('-revenue')[:limit])

    return {
        'period': label,
        'clients': [{
            'name': f"{c['client__first_name'] or ''} {c['client__last_name'] or ''}".strip() or 'Anonyme',
            'phone': c['client__phone'] or '-',
            'invoices': c['count'],
            'revenue': f"{c['revenue'] or 0} DH",
            'paid': f"{c['paid'] or 0} DH",
            'weight': f"{c['weight'] or 0}g",
        } for c in clients],
    }


def _fn_get_top_products(params):
    from sales.models import SaleInvoiceItem
    period = params.get('period', 'month')
    limit = params.get('limit', 10)
    start_date, end_date, label = _get_date_range(period)

    base = SaleInvoiceItem.objects.filter(
        invoice__is_deleted=False, invoice__date__gte=start_date,
        invoice__date__lte=end_date, product__isnull=False,
    ).exclude(invoice__status='returned')

    # Top by quantity sold
    products = list(base.values(
        'product__name', 'product__reference',
        'product__category__name', 'product__metal_type__name',
    ).annotate(
        qty=Sum('quantity'), revenue=Sum('total_amount'),
        count=Count('invoice', distinct=True),
    ).order_by('-qty')[:limit])

    return {
        'period': label,
        'products': [{
            'name': p['product__name'],
            'reference': p['product__reference'],
            'category': p['product__category__name'] or '-',
            'metal': p['product__metal_type__name'] or '-',
            'qty_sold': p['qty'] or 0,
            'revenue': f"{p['revenue'] or 0} DH",
            'invoices': p['count'],
        } for p in products],
    }


# ============ SALES / DASHBOARD FUNCTIONS ============

def _fn_get_sales_stats(params):
    from sales.models import SaleInvoice
    period = params.get('period', 'today')
    start_date, end_date, label = _get_date_range(period)

    qs = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date
    ).exclude(status='returned')

    stats = qs.aggregate(
        count=Count('id'), revenue=Sum('total_amount'), paid=Sum('amount_paid'),
        balance=Sum('balance_due'), discount=Sum('discount_amount'),
        weight=Sum('items__product__gross_weight'),
    )

    return {
        'period': label, 'invoices': stats['count'] or 0,
        'revenue': f"{stats['revenue'] or 0} DH", 'paid': f"{stats['paid'] or 0} DH",
        'balance_due': f"{stats['balance'] or 0} DH", 'discount': f"{stats['discount'] or 0} DH",
        'weight': f"{stats['weight'] or 0}g",
    }


def _fn_get_invoice_detail(params):
    from sales.models import SaleInvoice
    ref = params.get('reference', '')
    if not ref:
        return {'error': 'Référence facture requise'}
    try:
        inv = SaleInvoice.objects.select_related(
            'client', 'seller', 'payment_method'
        ).prefetch_related('items__product', 'payments').get(reference__iexact=ref)

        items = [{
            'product': item.product.name if item.product else '-',
            'ref': item.product.reference if item.product else '-',
            'price': f"{item.unit_price or 0} DH",
            'qty': item.quantity,
        } for item in inv.items.all()]

        payments = [{
            'amount': f"{p.amount} DH",
            'method': p.payment_method.name if p.payment_method else '-',
            'date': p.date.strftime('%d/%m/%Y') if p.date else '-',
        } for p in inv.payments.all()]

        delivery_info = '-'
        try:
            d = inv.delivery
            delivery_info = f"{d.get_status_display()} ({d.reference})"
            if d.tracking_number:
                delivery_info += f" - Suivi: {d.tracking_number}"
        except Exception:
            pass

        return {
            'reference': inv.reference,
            'date': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
            'client': inv.client.full_name if inv.client else 'Anonyme',
            'seller': inv.seller.get_full_name() if inv.seller else '-',
            'status': inv.get_status_display(),
            'total': f"{inv.total_amount or 0} DH",
            'paid': f"{inv.amount_paid or 0} DH",
            'balance': f"{inv.balance_due or 0} DH",
            'delivery_type': inv.get_delivery_method_type_display() if inv.delivery_method_type else 'Magasin',
            'delivery_status': delivery_info,
            'items': items,
            'payments': payments,
        }
    except SaleInvoice.DoesNotExist:
        return {'error': f'Facture {ref} introuvable'}


def _fn_get_dashboard_summary(params):
    from sales.models import SaleInvoice
    from payments.models import ClientPayment
    from deposits.models import DepositTransaction

    period = params.get('period', 'today')
    start_date, end_date, label = _get_date_range(period)

    sales_qs = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date
    ).exclude(status='returned')

    sales = sales_qs.aggregate(
        count=Count('id'), revenue=Sum('total_amount'), paid=Sum('amount_paid'),
        balance=Sum('balance_due'), discount=Sum('discount_amount'),
        old_gold=Sum('old_gold_amount'), weight=Sum('items__product__gross_weight'),
    )

    payments_qs = ClientPayment.objects.filter(
        sale_invoice__is_deleted=False, date__gte=start_date, date__lte=end_date,
    ).exclude(sale_invoice__status='returned')

    all_payments = payments_qs.exclude(payment_method__name='Dépôt Client').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    deposit_client = payments_qs.filter(payment_method__name='Dépôt Client').aggregate(total=Sum('amount'))['total'] or Decimal('0')

    amana_pending = payments_qs.filter(
        sale_invoice__delivery_method_type='amana',
    ).exclude(sale_invoice__delivery__status='delivered').exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    transport_pending = payments_qs.filter(
        sale_invoice__delivery_method_type='transporteur',
    ).exclude(sale_invoice__delivery__status='delivered').exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    real_encaisse = all_payments - amana_pending - transport_pending

    deposit_funds = DepositTransaction.objects.filter(
        transaction_type='deposit', date__gte=start_date, date__lte=end_date,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    return {
        'period': label,
        'invoices': sales['count'] or 0,
        'revenue': f"{sales['revenue'] or 0} DH",
        'weight': f"{sales['weight'] or 0}g",
        'encaisse': f"{real_encaisse} DH",
        'payments_total': f"{all_payments} DH",
        'deposit_client': f"{deposit_client} DH",
        'amana_pending': f"{amana_pending} DH",
        'transporteur_pending': f"{transport_pending} DH",
        'balance_due': f"{sales['balance'] or 0} DH",
        'discount': f"{sales['discount'] or 0} DH",
        'old_gold': f"{sales['old_gold'] or 0} DH",
        'deposit_funds': f"{deposit_funds} DH",
    }


# ============ PAYMENT FUNCTIONS ============

def _fn_get_payment_breakdown(params):
    from payments.models import ClientPayment
    period = params.get('period', 'today')
    start_date, end_date, label = _get_date_range(period)

    qs = ClientPayment.objects.filter(
        sale_invoice__is_deleted=False, date__gte=start_date, date__lte=end_date,
    ).exclude(sale_invoice__status='returned')

    methods = list(qs.values('payment_method__name').annotate(
        total=Sum('amount'), count=Count('id'),
    ).order_by('-total'))

    banks = list(qs.filter(bank_account__isnull=False).values(
        'bank_account__bank_name',
    ).annotate(total=Sum('amount'), count=Count('id')).order_by('-total'))

    total = qs.aggregate(total=Sum('amount'))['total'] or 0

    return {
        'period': label, 'total': f"{total} DH",
        'methods': [{'method': m['payment_method__name'] or 'Autre', 'total': f"{m['total']} DH", 'count': m['count']} for m in methods],
        'banks': [{'bank': b['bank_account__bank_name'], 'total': f"{b['total']} DH", 'count': b['count']} for b in banks],
    }


# ============ DELIVERY FUNCTIONS ============

def _fn_get_delivery_stats(params):
    from sales.models import SaleInvoice
    period = params.get('period', 'today')
    start_date, end_date, label = _get_date_range(period)

    base = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date,
    ).exclude(status='returned')

    magasin = base.filter(Q(delivery_method_type='magasin') | Q(delivery_method_type__isnull=True) | Q(delivery_method_type='')).aggregate(revenue=Sum('total_amount'), count=Count('id'))
    amana = base.filter(delivery_method_type='amana').aggregate(revenue=Sum('total_amount'), count=Count('id'))
    transporteur = base.filter(delivery_method_type='transporteur').aggregate(revenue=Sum('total_amount'), count=Count('id'))
    en_stock = base.filter(delivery_method_type='en_stock').aggregate(revenue=Sum('total_amount'), count=Count('id'))

    return {
        'period': label,
        'magasin': {'count': magasin['count'] or 0, 'revenue': f"{magasin['revenue'] or 0} DH"},
        'amana': {'count': amana['count'] or 0, 'revenue': f"{amana['revenue'] or 0} DH"},
        'transporteur': {'count': transporteur['count'] or 0, 'revenue': f"{transporteur['revenue'] or 0} DH"},
        'en_stock': {'count': en_stock['count'] or 0, 'revenue': f"{en_stock['revenue'] or 0} DH"},
    }


def _fn_get_delivery_status(params):
    from sales.models import Delivery
    ref = params.get('reference', '')
    if not ref:
        return {'error': 'Référence livraison requise'}

    try:
        d = Delivery.objects.select_related('invoice', 'invoice__client', 'carrier').get(
            Q(reference__iexact=ref) | Q(tracking_number__iexact=ref)
        )
        return {
            'reference': d.reference,
            'invoice': d.invoice.reference if d.invoice else '-',
            'client': d.client_name or (d.invoice.client.full_name if d.invoice and d.invoice.client else '-'),
            'phone': d.client_phone or '-',
            'status': d.get_status_display(),
            'type': d.get_delivery_method_type_display(),
            'carrier': d.carrier.name if d.carrier else '-',
            'tracking': d.tracking_number or '-',
            'amount': f"{d.total_amount or 0} DH",
            'cod': d.amount_cod or '-',
            'origin': d.origin or '-',
            'destination': d.destination or '-',
            'current_position': d.current_position or '-',
            'deposit_date': d.deposit_date or '-',
            'delivery_date': d.delivery_date or '-',
        }
    except Delivery.DoesNotExist:
        return {'error': f'Livraison {ref} introuvable'}
    except Delivery.MultipleObjectsReturned:
        deliveries = Delivery.objects.filter(
            Q(reference__icontains=ref) | Q(tracking_number__icontains=ref)
        )[:5]
        return [{
            'reference': d.reference, 'client': d.client_name,
            'status': d.get_status_display(), 'tracking': d.tracking_number or '-',
        } for d in deliveries]


def _fn_search_delivery(params):
    from sales.models import Delivery
    query = params.get('query', '')
    if not query:
        return {'error': 'Terme de recherche requis'}

    deliveries = Delivery.objects.filter(
        Q(client_name__icontains=query) | Q(client_phone__icontains=query) |
        Q(tracking_number__icontains=query) | Q(reference__icontains=query) |
        Q(destination__icontains=query)
    ).select_related('carrier').order_by('-created_at')[:10]

    return [{
        'reference': d.reference,
        'client': d.client_name,
        'phone': d.client_phone or '-',
        'status': d.get_status_display(),
        'type': d.get_delivery_method_type_display(),
        'tracking': d.tracking_number or '-',
        'amount': f"{d.total_amount or 0} DH",
        'destination': d.destination or '-',
    } for d in deliveries]


def _fn_get_pending_deliveries(params):
    from sales.models import SaleInvoice

    amana = SaleInvoice.objects.filter(
        is_deleted=False, delivery_method_type='amana',
    ).exclude(status='returned').exclude(delivery__status='delivered')
    amana_list = list(amana.select_related('client', 'seller', 'delivery').order_by('-date')[:20])
    amana_total = amana.aggregate(total=Sum('total_amount'))['total'] or 0

    transport = SaleInvoice.objects.filter(
        is_deleted=False, delivery_method_type='transporteur',
    ).exclude(status='returned').exclude(delivery__status='delivered')
    transport_list = list(transport.select_related('client', 'seller', 'delivery', 'carrier').order_by('-date')[:20])
    transport_total = transport.aggregate(total=Sum('total_amount'))['total'] or 0

    def _inv_info(inv):
        info = {
            'ref': inv.reference,
            'client': inv.client.full_name if inv.client else 'Anonyme',
            'amount': f"{inv.total_amount or 0} DH",
            'date': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
        }
        try:
            info['tracking'] = inv.delivery.tracking_number or '-'
            info['delivery_status'] = inv.delivery.get_status_display()
        except Exception:
            info['tracking'] = '-'
            info['delivery_status'] = 'Non créé'
        return info

    return {
        'amana': {'count': amana.count(), 'total': f"{amana_total} DH", 'invoices': [_inv_info(i) for i in amana_list[:10]]},
        'transporteur': {'count': transport.count(), 'total': f"{transport_total} DH", 'invoices': [_inv_info(i) for i in transport_list[:10]]},
        'total_pending': f"{amana_total + transport_total} DH",
    }


# ============ SELLER FUNCTIONS ============

def _fn_get_seller_performance(params):
    from sales.models import SaleInvoice
    period = params.get('period', 'today')
    start_date, end_date, label = _get_date_range(period)

    base = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date,
    ).exclude(status='returned')

    sellers = list(base.values(
        'seller__first_name', 'seller__last_name', 'seller__username'
    ).annotate(
        count=Count('id'), revenue=Sum('total_amount'),
        paid=Sum('amount_paid'), weight=Sum('items__product__gross_weight'),
    ).order_by('-revenue'))

    return {
        'period': label,
        'sellers': [{
            'name': f"{s['seller__first_name'] or ''} {s['seller__last_name'] or ''}".strip() or s['seller__username'],
            'invoices': s['count'],
            'revenue': f"{s['revenue'] or 0} DH",
            'paid': f"{s['paid'] or 0} DH",
            'weight': f"{s['weight'] or 0}g",
        } for s in sellers],
    }


# ============ PURCHASE FUNCTIONS ============

def _fn_get_purchase_stats(params):
    from purchases.models import PurchaseInvoice
    period = params.get('period', 'month')
    start_date, end_date, label = _get_date_range(period)

    qs = PurchaseInvoice.objects.filter(date__gte=start_date, date__lte=end_date)
    stats = qs.aggregate(count=Count('id'), total=Sum('total_amount'), paid=Sum('amount_paid'), balance=Sum('balance_due'))

    suppliers = list(qs.values('supplier__name').annotate(
        count=Count('id'), total=Sum('total_amount'), paid=Sum('amount_paid'),
    ).order_by('-total')[:10])

    return {
        'period': label,
        'invoices': stats['count'] or 0,
        'total': f"{stats['total'] or 0} DH",
        'paid': f"{stats['paid'] or 0} DH",
        'balance': f"{stats['balance'] or 0} DH",
        'suppliers': [{
            'name': s['supplier__name'] or 'Sans fournisseur',
            'invoices': s['count'], 'total': f"{s['total'] or 0} DH", 'paid': f"{s['paid'] or 0} DH",
        } for s in suppliers],
    }


# ============ REPAIR FUNCTIONS ============

def _fn_get_repair_stats(params):
    from repairs.models import Repair
    period = params.get('period', 'month')
    start_date, end_date, label = _get_date_range(period)

    qs = Repair.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

    total = qs.count()
    by_status = list(qs.values('status').annotate(count=Count('id')).order_by('-count'))
    revenue = qs.aggregate(total=Sum('estimated_cost'))['total'] or 0

    return {
        'period': label,
        'total': total,
        'revenue': f"{revenue} DH",
        'by_status': [{
            'status': s['status'], 'count': s['count'],
        } for s in by_status],
    }


# ============ AI RESPONSE FORMATTER (2nd pass) ============

FORMAT_PROMPT = """Tu es l'assistant IA de Bijouterie Hafsa. Tu reçois une question utilisateur et les données brutes du système.

Formule une réponse NATURELLE et CONVERSATIONNELLE en utilisant les données. Règles:
- Réponds dans la même langue que la question (darija, français, ou arabe)
- Si la question est en darija, réponds en darija/français mélangé naturellement
- Utilise des emojis pour structurer (📊💰👤📦🏆 etc.)
- Sois concis mais complet — montre les chiffres importants
- Pour les listes (top clients, produits, vendeurs), utilise un classement numéroté (1. 2. 3.)
- Pour les montants, garde le format "X DH"
- Ne dis JAMAIS que tu n'as pas accès aux données
- Si les données contiennent une erreur, explique-la simplement
- Maximum 2000 caractères pour la réponse
"""


def _ai_format_response(func_name, result, original_query):
    """Use AI to format function results into natural conversational response."""
    # Quick check for errors
    if isinstance(result, dict) and 'error' in result:
        return f"❌ {result['error']}"

    # Empty results
    if isinstance(result, list) and not result:
        return "Aucun résultat trouvé."

    # Prepare data summary for AI (truncate if too large)
    data_str = json.dumps(result, ensure_ascii=False, default=str)
    if len(data_str) > 3000:
        data_str = data_str[:3000] + '... (tronqué)'

    try:
        messages = [
            {'role': 'system', 'content': FORMAT_PROMPT},
            {'role': 'user', 'content': f"Question: {original_query}\n\nFonction appelée: {func_name}\n\nDonnées:\n{data_str}"},
        ]

        response = scaleway_client.chat_completion(
            messages=messages,
            model=scaleway_client.MODELS['chat'],
            temperature=0.3,
            max_tokens=1024,
        )
        return response.strip()
    except Exception as e:
        logger.error(f'AI format error: {e}')
        # Fallback to basic JSON dump
        return _fallback_format(func_name, result)


def _fallback_format(func_name, result):
    """Simple fallback formatter if the AI format pass fails."""
    if isinstance(result, dict):
        lines = []
        for k, v in result.items():
            if isinstance(v, (list, dict)):
                continue
            lines.append(f"• {k}: {v}")
        return '\n'.join(lines) if lines else json.dumps(result, ensure_ascii=False, indent=2)
    return json.dumps(result, ensure_ascii=False, indent=2)
