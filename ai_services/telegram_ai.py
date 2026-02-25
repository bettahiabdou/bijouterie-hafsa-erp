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
- "chhal dkhel lyoum?" = "combien on a encaissé aujourd'hui?"
- "chhal dkhel lbareh?" = "combien on a encaissé hier?"
- "chhal men khtem d dehab?" = "combien de bagues en or?"
- "3tini solde dyal client Ahmed" = "donne-moi le solde du client Ahmed"
- "wach kayn chi bracelet d 18K?" = "est-ce qu'il y a des bracelets en 18K?"
- "chno les ventes dyal lyoum?" = "quelles sont les ventes d'aujourd'hui?"
- "chkoun li ba3 kter had chher?" = "qui a le plus vendu ce mois?"
- "wach waslet la livraison dyal LIV-XXX?" = "est-ce que la livraison LIV-XXX est arrivée?"
- "feen waslet la commande dyal Fatima?" = "où en est la commande de Fatima?"

Tu dois répondre de manière concise et utile. Réponds en français sauf si l'utilisateur parle en darija ou arabe.

IMPORTANT: Tu as accès à TOUTES les données du système. Tu dois TOUJOURS appeler une fonction pour répondre — ne dis JAMAIS "je n'ai pas accès" ou "je ne peux pas". Si la question concerne des données, appelle la fonction la plus proche.

Pour répondre aux questions, retourne UNIQUEMENT un JSON avec la fonction à appeler:

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

9. get_dashboard_summary: Résumé complet (CA, encaissé réel, livraisons, paiements, dépôts)
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

18. general_answer: UNIQUEMENT pour les salutations et questions sans rapport avec les données
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

        return _format_result(func_name, params, result, text)

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


# ============ FORMATTERS ============

def _format_result(func_name, params, result, original_query):
    """Format function results into user-friendly text."""
    if isinstance(result, dict) and 'error' in result:
        return f"❌ {result['error']}"

    if func_name == 'search_products':
        if not result:
            return "Aucun produit trouvé."
        lines = [f"🔍 {len(result)} produit(s) trouvé(s):\n"]
        for p in result:
            lines.append(f"• {p['reference']} - {p['name']}")
            lines.append(f"  {p['metal']} | {p['weight']} | {p['price']}")
        return '\n'.join(lines)

    elif func_name == 'count_products':
        return f"📊 {result['count']} produit(s)\n   Poids: {result['total_weight']}\n   Valeur: {result['total_value']}"

    elif func_name == 'get_client_info':
        if not result:
            return "Client introuvable."
        lines = []
        for c in result:
            lines.append(f"👤 {c['name']} ({c['code']})")
            lines.append(f"   📱 {c['phone']}")
            lines.append(f"   💰 Dépôt: {c['deposit_balance']}")
        return '\n'.join(lines)

    elif func_name == 'get_client_sales':
        if not result:
            return "Client introuvable."
        lines = []
        for c in result:
            lines.append(f"👤 {c['client']} - {c['total_invoices']} factures")
            lines.append(f"   Total: {c['total_amount']} | Payé: {c['total_paid']}\n")
            for inv in c.get('invoices', [])[:5]:
                lines.append(f"   • {inv['ref']} ({inv['date']}) - {inv['amount']} [{inv['status']}]")
        return '\n'.join(lines)

    elif func_name == 'get_sales_stats':
        r = result
        return (
            f"📈 Ventes - {r['period']}:\n"
            f"   Factures: {r['invoices']}\n"
            f"   CA: {r['revenue']}\n"
            f"   Poids: {r['weight']}\n"
            f"   Encaissé: {r['paid']}\n"
            f"   Reste: {r['balance_due']}\n"
            f"   Remise: {r['discount']}"
        )

    elif func_name == 'get_product_by_ref':
        p = result
        return (
            f"📦 {p['reference']} - {p['name']}\n"
            f"   {p['metal']} | {p['weight']}\n"
            f"   Prix: {p['selling_price']} | Coût: {p['cost']}\n"
            f"   Statut: {p['status']}\n"
            f"   Fournisseur: {p['supplier']}\n"
            f"   Emplacement: {p['location']}"
        )

    elif func_name == 'get_invoice_detail':
        inv = result
        lines = [
            f"🧾 Facture {inv['reference']}",
            f"   Date: {inv['date']} | Statut: {inv['status']}",
            f"   Client: {inv['client']}",
            f"   Vendeur: {inv['seller']}",
            f"   Total: {inv['total']} | Payé: {inv['paid']} | Reste: {inv['balance']}",
            f"   Livraison: {inv['delivery_type']} - {inv['delivery_status']}",
        ]
        if inv.get('items'):
            lines.append(f"\n   Articles ({len(inv['items'])}):")
            for item in inv['items'][:8]:
                lines.append(f"   • {item['ref']} - {item['product']} × {item['qty']} = {item['price']}")
        if inv.get('payments'):
            lines.append(f"\n   Paiements ({len(inv['payments'])}):")
            for p in inv['payments']:
                lines.append(f"   • {p['amount']} ({p['method']}) - {p['date']}")
        return '\n'.join(lines)

    elif func_name == 'get_delivery_status':
        if isinstance(result, list):
            lines = [f"📦 {len(result)} livraisons trouvées:\n"]
            for d in result:
                lines.append(f"• {d['reference']} - {d['client']} - {d['status']} (Suivi: {d['tracking']})")
            return '\n'.join(lines)
        d = result
        lines = [
            f"📦 Livraison {d['reference']}",
            f"   Facture: {d['invoice']}",
            f"   Client: {d['client']} | 📱 {d['phone']}",
            f"   Statut: {d['status']}",
            f"   Type: {d['type']}",
        ]
        if d.get('carrier') and d['carrier'] != '-':
            lines.append(f"   Transporteur: {d['carrier']}")
        if d.get('tracking') and d['tracking'] != '-':
            lines.append(f"   Suivi: {d['tracking']}")
        lines.append(f"   Montant: {d['amount']}")
        if d.get('current_position') and d['current_position'] != '-':
            lines.append(f"   Position: {d['current_position']}")
        if d.get('destination') and d['destination'] != '-':
            lines.append(f"   Destination: {d['destination']}")
        return '\n'.join(lines)

    elif func_name == 'search_delivery':
        if not result:
            return "Aucune livraison trouvée."
        lines = [f"📦 {len(result)} livraison(s) trouvée(s):\n"]
        for d in result:
            lines.append(f"• {d['reference']} - {d['client']}")
            lines.append(f"  {d['status']} | {d['type']} | {d['amount']}")
            if d.get('tracking') and d['tracking'] != '-':
                lines.append(f"  Suivi: {d['tracking']}")
        return '\n'.join(lines)

    elif func_name == 'get_dashboard_summary':
        r = result
        return (
            f"📊 Tableau de bord - {r['period']}:\n\n"
            f"💰 CA: {r['revenue']} ({r['invoices']} factures)\n"
            f"⚖️ Poids: {r['weight']}\n"
            f"✅ Encaissé réel: {r['encaisse']}\n"
            f"💳 Paiements: {r['payments_total']}\n"
            f"🏦 Dépôt Client: {r['deposit_client']}\n"
            f"📦 AMANA en attente: {r['amana_pending']}\n"
            f"🚚 Transporteur en attente: {r['transporteur_pending']}\n"
            f"⏳ Reste à payer: {r['balance_due']}\n"
            f"🏷️ Remises: {r['discount']}\n"
            f"🪙 Or ancien: {r['old_gold']}\n"
            f"💵 Fonds dépôt reçus: {r['deposit_funds']}"
        )

    elif func_name == 'get_payment_breakdown':
        lines = [f"💳 Paiements - {result['period']}:\n", f"Total: {result['total']}\n"]
        for m in result.get('methods', []):
            lines.append(f"• {m['method']}: {m['total']} ({m['count']} paiements)")
        if result.get('banks'):
            lines.append(f"\n🏦 Par banque:")
            for b in result['banks']:
                lines.append(f"• {b['bank']}: {b['total']} ({b['count']})")
        return '\n'.join(lines)

    elif func_name == 'get_delivery_stats':
        r = result
        return (
            f"🚚 Livraisons - {r['period']}:\n\n"
            f"🏪 Magasin: {r['magasin']['count']} factures - {r['magasin']['revenue']}\n"
            f"📦 AMANA: {r['amana']['count']} factures - {r['amana']['revenue']}\n"
            f"🚛 Transporteur: {r['transporteur']['count']} factures - {r['transporteur']['revenue']}\n"
            f"🏢 En Stock: {r['en_stock']['count']} factures - {r['en_stock']['revenue']}"
        )

    elif func_name == 'get_seller_performance':
        lines = [f"👥 Performance vendeurs - {result['period']}:\n"]
        for i, s in enumerate(result.get('sellers', []), 1):
            lines.append(f"{i}. {s['name']}")
            lines.append(f"   {s['invoices']} factures | {s['revenue']} | {s['weight']}")
        if not result.get('sellers'):
            lines.append("Aucune vente pour cette période.")
        return '\n'.join(lines)

    elif func_name == 'get_pending_deliveries':
        a = result.get('amana', {})
        t = result.get('transporteur', {})
        lines = [f"📦 Livraisons en attente:\n"]
        lines.append(f"AMANA: {a.get('count', 0)} en attente - {a.get('total', '0 DH')}")
        for inv in a.get('invoices', [])[:5]:
            lines.append(f"  • {inv['ref']} - {inv['client']} - {inv['amount']} ({inv['date']})")
        lines.append(f"\nTransporteur: {t.get('count', 0)} en attente - {t.get('total', '0 DH')}")
        for inv in t.get('invoices', [])[:5]:
            lines.append(f"  • {inv['ref']} - {inv['client']} - {inv['amount']} ({inv['date']})")
        lines.append(f"\n💰 Total en attente: {result.get('total_pending', '0 DH')}")
        return '\n'.join(lines)

    elif func_name == 'get_purchase_stats':
        lines = [f"🛒 Achats - {result['period']}:\n"]
        lines.append(f"Factures: {result['invoices']} | Total: {result['total']}")
        lines.append(f"Payé: {result['paid']} | Reste: {result['balance']}")
        if result.get('suppliers'):
            lines.append(f"\nPar fournisseur:")
            for s in result['suppliers']:
                lines.append(f"• {s['name']}: {s['total']} ({s['invoices']} factures)")
        return '\n'.join(lines)

    elif func_name == 'get_inventory_summary':
        r = result
        lines = [
            f"📦 Stock disponible:\n",
            f"Total: {r['total_products']} produits",
            f"Poids: {r['total_weight']}",
            f"Valeur vente: {r['total_value']}",
            f"Coût: {r['total_cost']}",
        ]
        if r.get('by_category'):
            lines.append(f"\nPar catégorie:")
            for c in r['by_category'][:7]:
                lines.append(f"• {c['name']}: {c['count']} pcs - {c['weight']} - {c['value']}")
        if r.get('by_metal'):
            lines.append(f"\nPar métal:")
            for m in r['by_metal'][:5]:
                lines.append(f"• {m['name']}: {m['count']} pcs - {m['weight']} - {m['value']}")
        return '\n'.join(lines)

    elif func_name == 'get_repair_stats':
        lines = [f"🔧 Réparations - {result['period']}:\n"]
        lines.append(f"Total: {result['total']} | CA: {result['revenue']}")
        if result.get('by_status'):
            lines.append(f"\nPar statut:")
            for s in result['by_status']:
                lines.append(f"• {s['status']}: {s['count']}")
        return '\n'.join(lines)

    return json.dumps(result, ensure_ascii=False, indent=2)
