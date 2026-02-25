"""
AI-powered Telegram bot query handler for Bijouterie Hafsa ERP.
Supports French, Arabic (MSA), and Moroccan Darija.
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

Tu dois répondre de manière concise et utile. Réponds en français sauf si l'utilisateur parle en darija ou arabe.

Pour répondre aux questions, tu dois appeler une des fonctions suivantes. Retourne UNIQUEMENT un JSON avec la fonction à appeler:

FONCTIONS DISPONIBLES:

1. search_products: Chercher des produits
   {"function": "search_products", "params": {"query": "texte de recherche", "status": "available"}}

2. count_products: Compter des produits
   {"function": "count_products", "params": {"metal_type": "or/argent/...", "purity": "18K/21K/24K/925", "category": "bague/collier/bracelet/...", "status": "available"}}

3. get_client_info: Info client (solde, historique)
   {"function": "get_client_info", "params": {"name": "nom du client"}}

4. get_sales_stats: Statistiques de ventes
   {"function": "get_sales_stats", "params": {"period": "today/week/month"}}

5. get_product_by_ref: Chercher un produit par référence
   {"function": "get_product_by_ref", "params": {"reference": "REF-XXX"}}

6. general_answer: Pour les questions générales qui ne nécessitent pas de données
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
        if func_name == 'search_products':
            return _fn_search_products(params)
        elif func_name == 'count_products':
            return _fn_count_products(params)
        elif func_name == 'get_client_info':
            return _fn_get_client_info(params)
        elif func_name == 'get_sales_stats':
            return _fn_get_sales_stats(params)
        elif func_name == 'get_product_by_ref':
            return _fn_get_product_by_ref(params)
        elif func_name == 'general_answer':
            return params.get('answer', '')
        else:
            return {'error': f'Unknown function: {func_name}'}
    except Exception as e:
        logger.error(f'Function execution error ({func_name}): {e}')
        return {'error': str(e)}


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

    today = timezone.now().date()
    period = params.get('period', 'today')

    qs = SaleInvoice.objects.exclude(status='cancelled').exclude(is_deleted=True)

    if period == 'today':
        qs = qs.filter(date=today)
        period_label = "Aujourd'hui"
    elif period == 'week':
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())
        qs = qs.filter(date__gte=week_start)
        period_label = "Cette semaine"
    elif period == 'month':
        qs = qs.filter(date__year=today.year, date__month=today.month)
        period_label = "Ce mois"
    else:
        period_label = "Total"

    stats = qs.aggregate(
        count=Count('id'),
        revenue=Sum('total_amount'),
        paid=Sum('amount_paid'),
        balance=Sum('balance_due'),
    )

    return {
        'period': period_label,
        'invoices': stats['count'] or 0,
        'revenue': f"{stats['revenue'] or 0} DH",
        'paid': f"{stats['paid'] or 0} DH",
        'balance_due': f"{stats['balance'] or 0} DH",
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
            f"   Encaissé: {result['paid']}\n"
            f"   Reste: {result['balance_due']}"
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

    return json.dumps(result, ensure_ascii=False, indent=2)
