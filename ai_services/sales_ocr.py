"""
Sales photo OCR using Scaleway Vision AI.
Extracts product data from photos sent by salespeople via Telegram.
Handles: handwritten invoices, product photos, payment receipts.
Supports French, Arabic (MSA), and Moroccan Darija.
"""

import json
import logging
from . import scaleway_client

logger = logging.getLogger(__name__)

SALES_EXTRACTION_PROMPT = """Tu es un assistant spécialisé dans l'extraction de données de ventes de bijouterie au Maroc.

Analyse cette photo envoyée par un vendeur de bijouterie. La photo peut être:
- Une facture manuscrite de vente
- Une photo de bijoux (bagues, colliers, bracelets, boucles d'oreilles, etc.)
- Un bon de commande
- Un reçu de paiement
- Une note avec des informations client

Extrais les informations suivantes au format JSON strict:

{
    "photo_type": "invoice|product|payment|other",
    "client_name": "nom du client (si visible)",
    "client_phone": "numéro de téléphone (si visible)",
    "items": [
        {
            "description": "description du produit (type de bijou, métal, pureté si identifiable)",
            "category": "bague|collier|bracelet|boucle_oreille|chaine|pendentif|ensemble|montre|autre",
            "metal_type": "or|argent|plaqué_or|acier|autre|null",
            "purity": "18K|21K|24K|14K|9K|925|null",
            "weight": "poids estimé en grammes (nombre décimal, null si pas visible)",
            "quantity": 1,
            "unit_price": "prix en DH (nombre décimal, null si pas visible)"
        }
    ],
    "total_amount": "total en DH (nombre décimal, null si pas visible)",
    "payment_info": {
        "amount_paid": "montant payé (nombre décimal, null si pas visible)",
        "payment_method": "espèces|chèque|virement|carte|null",
        "reference": "numéro de chèque ou référence (si visible, sinon null)"
    },
    "notes": "autres informations utiles visibles"
}

Règles:
- Retourne UNIQUEMENT le JSON, pas de texte avant ou après
- Si une information n'est pas visible, mets null
- Les prix sont en Dirhams marocains (DH/MAD)
- Pour les bijoux, identifie: type (bague, collier, bracelet...), métal (or, argent), pureté (18K, 21K, 24K, 925)
- Si l'écriture est en arabe ou darija, traduis les descriptions en français
- Les poids sont en grammes
- Si l'écriture est manuscrite, fais de ton mieux pour déchiffrer
- Pour une photo de bijou sans texte, décris ce que tu vois (type, métal apparent, pierres)
"""


def extract_sales_data(image_path_or_bytes):
    """
    Extract structured data from a sales photo (handwritten invoice, product photo, etc.)

    Args:
        image_path_or_bytes: File path string or image bytes

    Returns:
        dict: Extracted sales data or error dict
    """
    if not scaleway_client.is_configured():
        return {'error': 'Service IA non configuré. Configurez SCALEWAY_AI_API_KEY dans .env'}

    try:
        response_text = scaleway_client.vision_completion(
            image_data=image_path_or_bytes,
            prompt=SALES_EXTRACTION_PROMPT,
            model=scaleway_client.MODELS['vision'],
            temperature=0.1,
            max_tokens=2048,
        )

        # Try to parse JSON from response
        clean_text = response_text.strip()
        if clean_text.startswith('```'):
            lines = clean_text.split('\n')
            clean_text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        data = json.loads(clean_text)
        return _clean_sales_data(data)

    except json.JSONDecodeError as e:
        logger.error(f'Failed to parse AI response as JSON: {e}')
        logger.error(f'Raw response: {response_text[:500]}')
        return {'error': f'Impossible de lire la réponse IA: {str(e)}', 'raw_response': response_text}
    except Exception as e:
        logger.error(f'Sales OCR error: {e}')
        return {'error': str(e)}


def _clean_sales_data(data):
    """Validate and clean extracted sales data."""
    cleaned = {
        'photo_type': data.get('photo_type', 'other'),
        'client_name': data.get('client_name') or '',
        'client_phone': data.get('client_phone') or '',
        'items': [],
        'total_amount': _to_decimal(data.get('total_amount')),
        'payment_info': {
            'amount_paid': _to_decimal((data.get('payment_info') or {}).get('amount_paid')),
            'payment_method': (data.get('payment_info') or {}).get('payment_method') or '',
            'reference': (data.get('payment_info') or {}).get('reference') or '',
        },
        'notes': data.get('notes') or '',
    }

    for item in data.get('items', []):
        cleaned_item = {
            'description': item.get('description', ''),
            'category': item.get('category', 'autre'),
            'metal_type': item.get('metal_type') or '',
            'purity': item.get('purity') or '',
            'weight': _to_decimal(item.get('weight')),
            'quantity': item.get('quantity', 1) or 1,
            'unit_price': _to_decimal(item.get('unit_price')),
        }
        cleaned['items'].append(cleaned_item)

    return cleaned


def _to_decimal(value):
    """Convert a value to a decimal string, or None."""
    if value is None:
        return None
    try:
        return str(round(float(value), 2))
    except (ValueError, TypeError):
        return None
