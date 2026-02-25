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

IMPORTANT: Analyse UNE SEULE photo à la fois. Extrais UNIQUEMENT ce qui est visible sur CETTE photo. Ne devine pas et n'invente pas de données.

Les types de photos les plus courants sont:

1. **BORDEREAU AMANA / BON DE LIVRAISON** (Poste Maroc / Barid Al Maghrib):
   C'est un formulaire imprimé avec des cases. Cherche:
   - **Numéro de bordereau**: nombre imprimé en ROUGE (souvent en haut, ex: 0020955). C'est le numéro de reçu AMANA.
   - **Code de suivi AMANA**: code-barres avec lettres+chiffres (format: 2 lettres + 8 chiffres + 2-3 lettres, ex: QB22606611SMA)
   - **Nom du destinataire**: champ "Destinataire" ou "المرسل إليه"
   - **Téléphone**: champ "Tél" ou numéro à 10 chiffres (06XX ou 07XX)
   - **Montant COD**: contre-remboursement (الثمن/المبلغ), souvent dans une case encadrée
   - **Ville destination**: champ "Destination" ou "Ville"
   - **Poids colis**: en kg ou g
   → Si c'est un bordereau AMANA: photo_type = "amana_slip", PAS d'items de bijoux

2. **REÇU / FACTURE BIJOUTERIE** (Bijouterie Hafsa ou autre):
   C'est un papier (souvent JAUNE) avec une liste de produits bijoux. Cherche:
   - **Numéro de facture/reçu**: souvent imprimé en ROUGE sur le papier jaune (ex: 0020955). C'est le numéro de la facture interne.
   - Descriptions en arabe ou français: خاتم=bague, سلسلة=chaîne, حلقات=boucles d'oreilles, سوار=bracelet, قلادة=collier, كورسيج=corsage/broche, دبلة=alliance, خلخال=chevillère
   - **Poids en grammes**: nombre décimal (ex: 3.5g, 4.2gr) - TRES IMPORTANT
   - **Prix**: en DH, parfois par gramme, parfois total
   - **Remise/تخفيض**: réduction appliquée
   - Calculs: prix original, remise, prix final (الباقي = reste/final)
   → Si c'est un reçu bijouterie: photo_type = "receipt", items avec poids et prix

3. **NOTE MANUSCRITE**: informations client, commande, etc.

ATTENTION à la lecture des caractères:
- Ne confonds PAS les chiffres et les lettres (5 ≠ S, 0 ≠ O, 1 ≠ I)
- Les numéros de téléphone marocains font 10 chiffres: 06XXXXXXXX ou 07XXXXXXXX
- Le code AMANA contient EXACTEMENT 8 chiffres entre les lettres

Extrais les informations au format JSON strict:

{
    "photo_type": "amana_slip|receipt|invoice|note|product_photo|other",
    "receipt_number": "numéro de facture/reçu imprimé en ROUGE sur le papier jaune (ex: 0020955)",
    "client_name": "nom du destinataire/client (si visible)",
    "client_phone": "téléphone 10 chiffres (si visible)",
    "client_city": "ville (si visible)",
    "delivery_info": {
        "tracking_number": "code de suivi AMANA (2 lettres + 8 chiffres + 2-3 lettres)",
        "bordereau_number": "numéro de bordereau AMANA (si différent du receipt_number)",
        "carrier": "amana|null",
        "cod_amount": "montant contre-remboursement en DH (nombre)",
        "destination": "ville de destination",
        "weight_package": "poids colis"
    },
    "items": [
        {
            "description": "description EN FRANCAIS (traduis l'arabe)",
            "category": "bague|collier|bracelet|boucle_oreille|chaine|pendentif|ensemble|montre|corsage|alliance|autre",
            "metal_type": "or|argent|plaqué_or|acier|autre|null",
            "purity": "18K|21K|24K|14K|9K|925|null",
            "weight_grams": "poids en grammes (nombre décimal, CRUCIAL)",
            "quantity": 1,
            "unit_price": "prix en DH (nombre)",
            "discount": "remise en DH (null si pas de remise)"
        }
    ],
    "total_amount": "total final en DH",
    "discount_total": "remise totale en DH",
    "payment_info": {
        "amount_paid": "montant payé",
        "payment_method": "espèces|chèque|virement|carte|null",
        "reference": "numéro de chèque ou ref"
    },
    "notes": "autres infos utiles (adresse, patente, dates, etc.)"
}

Règles STRICTES:
- Retourne UNIQUEMENT le JSON, rien d'autre
- Si une information n'est pas visible sur la photo, mets null — NE DEVINE PAS
- Si c'est un bordereau AMANA, NE METS PAS d'items bijoux (items = [])
- Si c'est un reçu bijouterie, NE METS PAS de delivery_info (tout null)
- Le NUMERO DE REÇU est imprimé en ROUGE sur le papier JAUNE (ex: 0020955) → receipt_number
- POIDS EN GRAMMES: pour les bijoux c'est la donnée la plus importante
- Traduis TOUJOURS l'arabe manuscrit en français
- Différencie bien les chiffres des lettres (5 ≠ S, 0 ≠ O, 1 ≠ I, 6 ≠ G)
- Numéros de téléphone marocains: TOUJOURS 10 chiffres commençant par 06 ou 07
- Le code de suivi AMANA a EXACTEMENT 8 chiffres entre les lettres (ex: QB22606611SMA)
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
        'receipt_number': (data.get('receipt_number') or '').strip(),
        'client_name': data.get('client_name') or '',
        'client_phone': data.get('client_phone') or '',
        'client_city': data.get('client_city') or '',
        'delivery_info': {
            'tracking_number': (delivery.get('tracking_number') or '').strip(),
            'bordereau_number': (delivery.get('bordereau_number') or '').strip(),
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
