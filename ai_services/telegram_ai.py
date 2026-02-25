"""
AI-powered query handler for Bijouterie Hafsa ERP.
Supports French, Arabic (MSA), and Moroccan Darija.
Used by Telegram bot AND web admin chat.
"""

import json
import logging
from decimal import Decimal
from django.db.models import Q, Sum, Count
from django.utils import timezone

from . import scaleway_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'assistant IA de Bijouterie Hafsa, une bijouterie au Maroc. Tu aides le personnel du magasin à trouver des informations rapidement.

Tu comprends le français, l'arabe standard, et le darija marocain. Exemples en darija:
- "chhal men khtem d dehab?" = "combien de bagues en or?"
- "3tini solde dyal client Ahmed" = "donne-moi le solde du client Ahmed"
- "wach kayn chi bracelet d 18K?" = "est-ce qu'il y a des bracelets en 18K?"
- "chno les ventes dyal lyoum?" = "quelles sont les ventes d'aujourd'hui?"
- "chhal dkhel lyoum?" = "combien on a encaissé aujourd'hui?"
- "chkoun li ba3 kter had chher?" = "qui a le plus vendu ce mois?"

Tu dois répondre de manière concise et utile. Réponds en français sauf si l'utilisateur parle en darija ou arabe.

Pour répondre aux questions, tu dois appeler une des fonctions suivantes. Retourne UNIQUEMENT un JSON avec la fonction à appeler:

FONCTIONS DISPONIBLES:

1. search_products: Chercher des produits
   {"function": "search_products", "params": {"query": "texte de recherche", "status": "available"}}

2. count_products: Compter des produits
   {"function": "count_products", "params": {"metal_type": "or/argent/...", "purity": "18K/21K/24K/925", "category": "bague/collier/bracelet/...", "status": "available"}}

3. get_client_info: Info client (solde, historique)
   {"function": "get_client_info", "params": {"name": "nom du client"}}

4. get_sales_stats: Statistiques de ventes (CA, factures, poids)
   {"function": "get_sales_stats", "params": {"period": "today/week/month"}}

5. get_product_by_ref: Chercher un produit par référence
   {"function": "get_product_by_ref", "params": {"reference": "REF-XXX"}}

6. get_dashboard_summary: Résumé complet du tableau de bord (CA, encaissé, livraisons, paiements)
   {"function": "get_dashboard_summary", "params": {"period": "today/month"}}

7. get_payment_breakdown: Détail des paiements par méthode (espèces, virement, chèque, etc.)
   {"function": "get_payment_breakdown", "params": {"period": "today/month"}}

8. get_delivery_stats: Statistiques de livraison (magasin, AMANA, transporteur, en stock)
   {"function": "get_delivery_stats", "params": {"period": "today/month"}}

9. get_seller_performance: Performance des vendeurs
   {"function": "get_seller_performance", "params": {"period": "today/month"}}

10. get_pending_deliveries: Livraisons en attente (AMANA + transporteur non livrées)
    {"function": "get_pending_deliveries", "params": {}}

11. get_purchase_stats: Statistiques des achats fournisseurs
    {"function": "get_purchase_stats", "params": {"period": "today/month"}}

12. general_answer: Pour les questions générales qui ne nécessitent pas de données
    {"function": "general_answer", "params": {"answer": "ta réponse ici"}}

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
        # Step 1: Ask AI to determine which function to call
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

        # Step 2: Parse the function call
        clean = response.strip()
        if clean.startswith('```'):
            lines = clean.split('\n')
            clean = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        function_call = json.loads(clean)
        func_name = function_call.get('function', 'general_answer')
        params = function_call.get('params', {})

        # Step 3: Execute the function
        result = _execute_function(func_name, params)

        # Step 4: Format the result for the user
        if func_name == 'general_answer':
            return params.get('answer', result)

        return _format_result(func_name, params, result, text)

    except json.JSONDecodeError:
        # AI didn't return valid JSON — treat response as direct answer
        return response if response else "Désolé, je n'ai pas compris. Essayez de reformuler."
    except Exception as e:
        logger.error(f'AI query error: {e}')
        return f"Erreur: {str(e)}"


def _execute_function(func_name, params):
    """Execute a database function based on AI's decision."""
    try:
        handlers = {
            'search_products': _fn_search_products,
            'count_products': _fn_count_products,
            'get_client_info': _fn_get_client_info,
            'get_sales_stats': _fn_get_sales_stats,
            'get_product_by_ref': _fn_get_product_by_ref,
            'get_dashboard_summary': _fn_get_dashboard_summary,
            'get_payment_breakdown': _fn_get_payment_breakdown,
            'get_delivery_stats': _fn_get_delivery_stats,
            'get_seller_performance': _fn_get_seller_performance,
            'get_pending_deliveries': _fn_get_pending_deliveries,
            'get_purchase_stats': _fn_get_purchase_stats,
            'general_answer': lambda p: p.get('answer', ''),
        }

        handler = handlers.get(func_name)
        if handler:
            return handler(params)
        return {'error': f'Unknown function: {func_name}'}
    except Exception as e:
        logger.error(f'Function execution error ({func_name}): {e}')
        return {'error': str(e)}


# ============ Helper: get date range from period ============

def _get_date_range(period):
    """Return (start_date, label) for a period string."""
    from datetime import timedelta
    today = timezone.now().date()

    if period == 'today':
        return today, today, "Aujourd'hui"
    elif period == 'week':
        week_start = today - timedelta(days=today.weekday())
        return week_start, today, "Cette semaine"
    elif period == 'month':
        month_start = today.replace(day=1)
        return month_start, today, "Ce mois"
    elif period == 'year':
        year_start = today.replace(month=1, day=1)
        return year_start, today, "Cette année"
    else:
        return today.replace(day=1), today, "Ce mois"


# ============ ORIGINAL FUNCTIONS ============

def _fn_search_products(params):
    """Search products by text query."""
    from products.models import Product

    query = params.get('query', '')
    status = params.get('status', 'available')

    qs = Product.objects.select_related('category', 'metal_type', 'metal_purity')
    if status:
        qs = qs.filter(status=status)

    if query:
        qs = qs.filter(
            Q(name__icontains=query) |
            Q(name_ar__icontains=query) |
            Q(reference__icontains=query) |
            Q(category__name__icontains=query) |
            Q(description__icontains=query)
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
    """Count products with optional filters."""
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


def _fn_get_client_info(params):
    """Get client information including deposit balance."""
    from clients.models import Client
    from deposits.models import DepositAccount

    name = params.get('name', '')
    if not name:
        return {'error': 'Nom du client requis'}

    clients = Client.objects.filter(
        Q(first_name__icontains=name) |
        Q(last_name__icontains=name) |
        Q(phone__icontains=name)
    )[:5]

    results = []
    for c in clients:
        info = {
            'name': c.full_name,
            'phone': c.phone or '-',
            'code': c.code,
        }
        # Check deposit balance
        try:
            deposit = DepositAccount.objects.get(client=c)
            info['deposit_balance'] = f'{deposit.balance} DH'
        except DepositAccount.DoesNotExist:
            info['deposit_balance'] = 'Pas de compte dépôt'

        results.append(info)

    return results


def _fn_get_sales_stats(params):
    """Get sales statistics for a period."""
    from sales.models import SaleInvoice

    period = params.get('period', 'today')
    start_date, end_date, period_label = _get_date_range(period)

    qs = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date
    ).exclude(status='returned')

    stats = qs.aggregate(
        count=Count('id'),
        revenue=Sum('total_amount'),
        paid=Sum('amount_paid'),
        balance=Sum('balance_due'),
        discount=Sum('discount_amount'),
        weight=Sum('items__product__gross_weight'),
    )

    return {
        'period': period_label,
        'invoices': stats['count'] or 0,
        'revenue': f"{stats['revenue'] or 0} DH",
        'paid': f"{stats['paid'] or 0} DH",
        'balance_due': f"{stats['balance'] or 0} DH",
        'discount': f"{stats['discount'] or 0} DH",
        'weight': f"{stats['weight'] or 0}g",
    }


def _fn_get_product_by_ref(params):
    """Find a product by its reference."""
    from products.models import Product

    ref = params.get('reference', '')
    if not ref:
        return {'error': 'Référence requise'}

    try:
        p = Product.objects.select_related(
            'category', 'metal_type', 'metal_purity', 'supplier'
        ).get(reference__iexact=ref)

        return {
            'reference': p.reference,
            'name': p.name,
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


# ============ NEW DASHBOARD FUNCTIONS ============

def _fn_get_dashboard_summary(params):
    """Get comprehensive dashboard summary with all key metrics."""
    from sales.models import SaleInvoice
    from payments.models import ClientPayment
    from deposits.models import DepositTransaction

    period = params.get('period', 'today')
    start_date, end_date, period_label = _get_date_range(period)

    # Sales
    sales_qs = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date
    ).exclude(status='returned')

    sales_stats = sales_qs.aggregate(
        count=Count('id'),
        revenue=Sum('total_amount'),
        paid=Sum('amount_paid'),
        balance=Sum('balance_due'),
        discount=Sum('discount_amount'),
        old_gold=Sum('old_gold_amount'),
        weight=Sum('items__product__gross_weight'),
    )

    # Payments (by payment date)
    payments_qs = ClientPayment.objects.filter(
        sale_invoice__is_deleted=False,
        date__gte=start_date, date__lte=end_date,
    ).exclude(sale_invoice__status='returned')

    all_payments = payments_qs.exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    deposit_client = payments_qs.filter(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Pending deliveries (not yet received)
    amana_pending = payments_qs.filter(
        sale_invoice__delivery_method_type='amana',
    ).exclude(sale_invoice__delivery__status='delivered').exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    transporteur_pending = payments_qs.filter(
        sale_invoice__delivery_method_type='transporteur',
    ).exclude(sale_invoice__delivery__status='delivered').exclude(
        payment_method__name='Dépôt Client'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    real_encaisse = all_payments - amana_pending - transporteur_pending

    # Deposit funds received
    deposit_funds = DepositTransaction.objects.filter(
        transaction_type='deposit',
        date__gte=start_date, date__lte=end_date,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    return {
        'period': period_label,
        'invoices': sales_stats['count'] or 0,
        'revenue': f"{sales_stats['revenue'] or 0} DH",
        'weight': f"{sales_stats['weight'] or 0}g",
        'encaisse': f"{real_encaisse} DH",
        'payments_total': f"{all_payments} DH",
        'deposit_client': f"{deposit_client} DH",
        'amana_pending': f"{amana_pending} DH",
        'transporteur_pending': f"{transporteur_pending} DH",
        'balance_due': f"{sales_stats['balance'] or 0} DH",
        'discount': f"{sales_stats['discount'] or 0} DH",
        'old_gold': f"{sales_stats['old_gold'] or 0} DH",
        'deposit_funds': f"{deposit_funds} DH",
    }


def _fn_get_payment_breakdown(params):
    """Get payment breakdown by method."""
    from payments.models import ClientPayment

    period = params.get('period', 'today')
    start_date, end_date, period_label = _get_date_range(period)

    payments_qs = ClientPayment.objects.filter(
        sale_invoice__is_deleted=False,
        date__gte=start_date, date__lte=end_date,
    ).exclude(sale_invoice__status='returned')

    breakdown = list(
        payments_qs.values('payment_method__name').annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('-total')
    )

    # Bank account breakdown
    bank_breakdown = list(
        payments_qs.filter(bank_account__isnull=False).values(
            'bank_account__bank_name',
        ).annotate(
            total=Sum('amount'),
            count=Count('id'),
        ).order_by('-total')
    )

    total = payments_qs.aggregate(total=Sum('amount'))['total'] or 0

    return {
        'period': period_label,
        'total': f"{total} DH",
        'methods': [{
            'method': m['payment_method__name'] or 'Autre',
            'total': f"{m['total']} DH",
            'count': m['count'],
        } for m in breakdown],
        'banks': [{
            'bank': b['bank_account__bank_name'],
            'total': f"{b['total']} DH",
            'count': b['count'],
        } for b in bank_breakdown],
    }


def _fn_get_delivery_stats(params):
    """Get delivery type breakdown."""
    from sales.models import SaleInvoice

    period = params.get('period', 'today')
    start_date, end_date, period_label = _get_date_range(period)

    base_qs = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date,
    ).exclude(status='returned')

    magasin = base_qs.filter(
        Q(delivery_method_type='magasin') | Q(delivery_method_type__isnull=True) | Q(delivery_method_type='')
    ).aggregate(revenue=Sum('total_amount'), count=Count('id'))

    amana = base_qs.filter(delivery_method_type='amana').aggregate(
        revenue=Sum('total_amount'), count=Count('id'))

    transporteur = base_qs.filter(delivery_method_type='transporteur').aggregate(
        revenue=Sum('total_amount'), count=Count('id'))

    en_stock = base_qs.filter(delivery_method_type='en_stock').aggregate(
        revenue=Sum('total_amount'), count=Count('id'))

    return {
        'period': period_label,
        'magasin': {'count': magasin['count'] or 0, 'revenue': f"{magasin['revenue'] or 0} DH"},
        'amana': {'count': amana['count'] or 0, 'revenue': f"{amana['revenue'] or 0} DH"},
        'transporteur': {'count': transporteur['count'] or 0, 'revenue': f"{transporteur['revenue'] or 0} DH"},
        'en_stock': {'count': en_stock['count'] or 0, 'revenue': f"{en_stock['revenue'] or 0} DH"},
    }


def _fn_get_seller_performance(params):
    """Get seller performance stats."""
    from sales.models import SaleInvoice

    period = params.get('period', 'today')
    start_date, end_date, period_label = _get_date_range(period)

    base_qs = SaleInvoice.objects.filter(
        is_deleted=False, date__gte=start_date, date__lte=end_date,
    ).exclude(status='returned')

    sellers = list(
        base_qs.values(
            'seller__first_name', 'seller__last_name', 'seller__username'
        ).annotate(
            count=Count('id'),
            revenue=Sum('total_amount'),
            paid=Sum('amount_paid'),
            weight=Sum('items__product__gross_weight'),
        ).order_by('-revenue')
    )

    return {
        'period': period_label,
        'sellers': [{
            'name': f"{s['seller__first_name'] or ''} {s['seller__last_name'] or ''}".strip() or s['seller__username'],
            'invoices': s['count'],
            'revenue': f"{s['revenue'] or 0} DH",
            'paid': f"{s['paid'] or 0} DH",
            'weight': f"{s['weight'] or 0}g",
        } for s in sellers],
    }


def _fn_get_pending_deliveries(params):
    """Get pending deliveries (not yet delivered)."""
    from sales.models import SaleInvoice

    # AMANA pending
    amana_pending = SaleInvoice.objects.filter(
        is_deleted=False, delivery_method_type='amana',
    ).exclude(status='returned').exclude(delivery__status='delivered')

    amana_list = list(
        amana_pending.select_related('client', 'seller')
        .order_by('-date')[:20]
    )
    amana_total = amana_pending.aggregate(total=Sum('total_amount'))['total'] or 0

    # Transporteur pending
    transport_pending = SaleInvoice.objects.filter(
        is_deleted=False, delivery_method_type='transporteur',
    ).exclude(status='returned').exclude(delivery__status='delivered')

    transport_list = list(
        transport_pending.select_related('client', 'seller', 'carrier')
        .order_by('-date')[:20]
    )
    transport_total = transport_pending.aggregate(total=Sum('total_amount'))['total'] or 0

    return {
        'amana': {
            'count': len(amana_list),
            'total': f"{amana_total} DH",
            'invoices': [{
                'ref': inv.reference,
                'client': inv.client.full_name if inv.client else 'Anonyme',
                'amount': f"{inv.total_amount or 0} DH",
                'date': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
            } for inv in amana_list[:10]],
        },
        'transporteur': {
            'count': len(transport_list),
            'total': f"{transport_total} DH",
            'invoices': [{
                'ref': inv.reference,
                'client': inv.client.full_name if inv.client else 'Anonyme',
                'amount': f"{inv.total_amount or 0} DH",
                'date': inv.date.strftime('%d/%m/%Y') if inv.date else '-',
                'carrier': inv.carrier.name if inv.carrier else '-',
            } for inv in transport_list[:10]],
        },
        'total_pending': f"{amana_total + transport_total} DH",
    }


def _fn_get_purchase_stats(params):
    """Get purchase invoice statistics."""
    from purchases.models import PurchaseInvoice

    period = params.get('period', 'month')
    start_date, end_date, period_label = _get_date_range(period)

    qs = PurchaseInvoice.objects.filter(
        date__gte=start_date, date__lte=end_date,
    )

    stats = qs.aggregate(
        count=Count('id'),
        total=Sum('total_amount'),
        paid=Sum('amount_paid'),
        balance=Sum('balance_due'),
    )

    # Per-supplier breakdown
    suppliers = list(
        qs.values('supplier__name').annotate(
            count=Count('id'),
            total=Sum('total_amount'),
            paid=Sum('amount_paid'),
        ).order_by('-total')[:10]
    )

    return {
        'period': period_label,
        'invoices': stats['count'] or 0,
        'total': f"{stats['total'] or 0} DH",
        'paid': f"{stats['paid'] or 0} DH",
        'balance': f"{stats['balance'] or 0} DH",
        'suppliers': [{
            'name': s['supplier__name'] or 'Sans fournisseur',
            'invoices': s['count'],
            'total': f"{s['total'] or 0} DH",
            'paid': f"{s['paid'] or 0} DH",
        } for s in suppliers],
    }


# ============ FORMATTERS ============

def _format_result(func_name, params, result, original_query):
    """Format function results into user-friendly text."""
    if isinstance(result, dict) and 'error' in result:
        return f"Erreur: {result['error']}"

    if func_name == 'search_products':
        if not result:
            return "Aucun produit trouvé."
        lines = [f"🔍 {len(result)} produit(s) trouvé(s):\n"]
        for p in result:
            lines.append(f"• {p['reference']} - {p['name']}")
            lines.append(f"  {p['metal']} | {p['weight']} | {p['price']}")
        return '\n'.join(lines)

    elif func_name == 'count_products':
        return (
            f"📊 {result['count']} produit(s)\n"
            f"   Poids total: {result['total_weight']}\n"
            f"   Valeur: {result['total_value']}"
        )

    elif func_name == 'get_client_info':
        if not result:
            return "Client introuvable."
        lines = []
        for c in result:
            lines.append(f"👤 {c['name']} ({c['code']})")
            lines.append(f"   📱 {c['phone']}")
            lines.append(f"   💰 Dépôt: {c['deposit_balance']}")
        return '\n'.join(lines)

    elif func_name == 'get_sales_stats':
        return (
            f"📈 Ventes - {result['period']}:\n"
            f"   Factures: {result['invoices']}\n"
            f"   CA: {result['revenue']}\n"
            f"   Poids: {result['weight']}\n"
            f"   Encaissé: {result['paid']}\n"
            f"   Reste: {result['balance_due']}\n"
            f"   Remise: {result['discount']}"
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

    elif func_name == 'get_dashboard_summary':
        return (
            f"📊 Tableau de bord - {result['period']}:\n\n"
            f"💰 CA: {result['revenue']} ({result['invoices']} factures)\n"
            f"⚖️ Poids: {result['weight']}\n"
            f"✅ Encaissé réel: {result['encaisse']}\n"
            f"💳 Paiements: {result['payments_total']}\n"
            f"🏦 Dépôt Client: {result['deposit_client']}\n"
            f"📦 AMANA en attente: {result['amana_pending']}\n"
            f"🚚 Transporteur en attente: {result['transporteur_pending']}\n"
            f"⏳ Reste à payer: {result['balance_due']}\n"
            f"🏷️ Remises: {result['discount']}\n"
            f"🪙 Or ancien: {result['old_gold']}\n"
            f"💵 Fonds dépôt reçus: {result['deposit_funds']}"
        )

    elif func_name == 'get_payment_breakdown':
        lines = [f"💳 Paiements - {result['period']}:\n"]
        lines.append(f"Total: {result['total']}\n")
        for m in result.get('methods', []):
            lines.append(f"• {m['method']}: {m['total']} ({m['count']} paiements)")
        if result.get('banks'):
            lines.append(f"\n🏦 Par banque:")
            for b in result['banks']:
                lines.append(f"• {b['bank']}: {b['total']} ({b['count']})")
        return '\n'.join(lines)

    elif func_name == 'get_delivery_stats':
        return (
            f"🚚 Livraisons - {result['period']}:\n\n"
            f"🏪 Magasin: {result['magasin']['count']} factures - {result['magasin']['revenue']}\n"
            f"📦 AMANA: {result['amana']['count']} factures - {result['amana']['revenue']}\n"
            f"🚛 Transporteur: {result['transporteur']['count']} factures - {result['transporteur']['revenue']}\n"
            f"🏢 En Stock: {result['en_stock']['count']} factures - {result['en_stock']['revenue']}"
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
        lines = [f"📦 Livraisons en attente:\n"]
        a = result.get('amana', {})
        t = result.get('transporteur', {})
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
        lines.append(f"Factures: {result['invoices']}")
        lines.append(f"Total: {result['total']}")
        lines.append(f"Payé: {result['paid']}")
        lines.append(f"Reste: {result['balance']}")
        if result.get('suppliers'):
            lines.append(f"\nPar fournisseur:")
            for s in result['suppliers']:
                lines.append(f"• {s['name']}: {s['total']} ({s['invoices']} factures)")
        return '\n'.join(lines)

    return json.dumps(result, ensure_ascii=False, indent=2)
