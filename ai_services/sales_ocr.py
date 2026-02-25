"""
Sales photo OCR using Scaleway Vision AI.
Extracts product data from photos sent by salespeople via Telegram.
Handles: AMANA delivery slips, sales receipts, handwritten notes.
Supports French, Arabic (MSA), and Moroccan Darija.
"""

import json
import logging
from . import scaleway_client

logger = logging.getLogger(__name__)

SALES_EXTRACTION_PROMPT = """Tu es un assistant spécialisé dans l'extraction de données de ventes de bijouterie au Maroc.

Analyse cette photo envoyée par un vendeur. Les types de photos les plus courants sont:

1. **BORDEREAU AMANA / BON DE LIVRAISON** (Poste Maroc / Barid Al Maghrib):
   - Code de suivi AMANA (format: 2 lettres + 8 chiffres + 2 lettres, ex: QB22606611SMA)
   - Nom du destinataire / expéditeur
   - Numéro de téléphone
   - Montant contre-remboursement (COD/الثمن/المبلغ)
   - Ville de destination
   - Poids du colis
   → PRIORITE: Extraire le code de suivi AMANA est CRUCIAL

2. **REÇU / FACTURE BIJOUTERIE** (Bijouterie Hafsa ou autre):
   - Liste des produits avec description en français OU arabe (خاتم=bague, سلسلة=chaine, حلقات=boucles, سوار=bracelet, قلادة=collier, كورسيج=corsage/broche)
   - Poids en grammes (très important pour la bijouterie)
   - Prix par article
   - Remise/تخفيض (discount)
   - Total
   → PRIORITE: Extraire le poids en grammes et le prix de chaque article

3. **NOTE MANUSCRITE / BON DE COMMANDE**:
   - Informations client (nom, téléphone, ville)
   - Liste de produits commandés
   - Prix et poids

Extrais les informations au format JSON strict:

{
    "photo_type": "amana_slip|receipt|invoice|note|product_photo|other",
    "client_name": "nom du client/destinataire (si visible)",
    "client_phone": "numéro de téléphone (si visible, format: 06XXXXXXXX)",
    "client_city": "ville du client (si visible)",
    "delivery_info": {
        "tracking_number": "code de suivi AMANA ou transporteur (CRUCIAL - ex: QB22606611SMA)",
        "carrier": "amana|autre transporteur|null",
        "cod_amount": "montant contre-remboursement en DH (nombre décimal, null si pas visible)",
        "destination": "ville de destination",
        "weight_package": "poids du colis (si visible)"
    },
    "items": [
        {
            "description": "description du produit EN FRANCAIS (traduis l'arabe)",
            "category": "bague|collier|bracelet|boucle_oreille|chaine|pendentif|ensemble|montre|corsage|autre",
            "metal_type": "or|argent|plaqué_or|acier|autre|null",
            "purity": "18K|21K|24K|14K|9K|925|null",
            "weight_grams": "poids en grammes (nombre décimal, TRES IMPORTANT pour bijouterie)",
            "quantity": 1,
            "unit_price": "prix unitaire en DH (nombre décimal)",
            "discount": "montant de remise en DH sur cet article (null si pas de remise)"
        }
    ],
    "total_amount": "total en DH (nombre décimal)",
    "discount_total": "remise totale en DH (si visible)",
    "payment_info": {
        "amount_paid": "montant payé (nombre décimal)",
        "payment_method": "espèces|chèque|virement|carte|null",
        "reference": "numéro de chèque ou référence (sinon null)"
    },
    "notes": "autres informations utiles (adresse, patente, dates, etc.)"
}

Règles STRICTES:
- Retourne UNIQUEMENT le JSON, pas de texte avant ou après
- Si une information n'est pas visible, mets null
- Les prix sont en DH (Dirhams marocains)
- POIDS EN GRAMMES: c'est l'information la plus importante pour les bijoux, cherche bien
- CODE AMANA: format typique 2 lettres + 8 chiffres + 2-3 lettres (ex: QB22606611SMA)
- Traduis TOUJOURS les descriptions arabes en français
- Si écriture manuscrite, fais de ton mieux pour déchiffrer les chiffres (poids et prix)
- Si tu vois un bordereau AMANA, le photo_type DOIT être "amana_slip"
- Pour le COD (contre-remboursement), cherche الثمن ou المبلغ ou le montant encadré
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
    delivery = data.get('delivery_info') or {}

    cleaned = {
        'photo_type': data.get('photo_type', 'other'),
        'client_name': data.get('client_name') or '',
        'client_phone': data.get('client_phone') or '',
        'client_city': data.get('client_city') or '',
        'delivery_info': {
            'tracking_number': (delivery.get('tracking_number') or '').strip(),
            'carrier': delivery.get('carrier') or '',
            'cod_amount': _to_decimal(delivery.get('cod_amount')),
            'destination': delivery.get('destination') or '',
            'weight_package': delivery.get('weight_package') or '',
        },
        'items': [],
        'total_amount': _to_decimal(data.get('total_amount')),
        'discount_total': _to_decimal(data.get('discount_total')),
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
            'weight': _to_decimal(item.get('weight_grams') or item.get('weight')),
            'quantity': item.get('quantity', 1) or 1,
            'unit_price': _to_decimal(item.get('unit_price')),
            'discount': _to_decimal(item.get('discount')),
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
