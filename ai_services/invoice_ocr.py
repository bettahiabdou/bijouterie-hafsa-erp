"""
Purchase invoice photo OCR using Scaleway Vision AI.
Extracts structured data from invoice photos to auto-fill forms.
"""

import json
import logging
from . import scaleway_client

logger = logging.getLogger(__name__)

INVOICE_EXTRACTION_PROMPT = """Tu es un assistant spécialisé dans l'extraction de données de factures d'achat de bijouterie au Maroc.

Analyse cette photo de facture et extrais les informations suivantes au format JSON strict:

{
    "supplier_name": "nom du fournisseur (si visible)",
    "invoice_number": "numéro de facture (si visible)",
    "date": "date au format YYYY-MM-DD (si visible)",
    "items": [
        {
            "description": "description du produit (type de bijou, métal, pureté)",
            "reference": "référence produit si visible",
            "weight": "poids en grammes (nombre décimal, null si pas visible)",
            "quantity": 1,
            "unit_price": "prix unitaire en DH (nombre décimal, null si pas visible)",
            "total_price": "prix total en DH (nombre décimal, null si pas visible)"
        }
    ],
    "subtotal": "sous-total en DH (nombre décimal, null si pas visible)",
    "tax_amount": "montant TVA en DH (nombre décimal, null si pas visible)",
    "total_amount": "total TTC en DH (nombre décimal, null si pas visible)",
    "notes": "autres informations utiles visibles sur la facture"
}

Règles:
- Retourne UNIQUEMENT le JSON, pas de texte avant ou après
- Si une information n'est pas visible, mets null
- Les prix sont en Dirhams marocains (DH/MAD)
- Pour les bijoux, essaie d'identifier: type (bague, collier, bracelet...), métal (or, argent), pureté (18K, 21K, 24K, 925)
- Les poids sont généralement en grammes
- Si l'écriture est manuscrite, fais de ton mieux pour déchiffrer
"""


def extract_invoice_data(image_path_or_bytes):
    """
    Extract structured data from a purchase invoice photo.

    Args:
        image_path_or_bytes: File path string or image bytes

    Returns:
        dict: Extracted invoice data or error dict
    """
    if not scaleway_client.is_configured():
        return {'error': 'AI service not configured. Set SCALEWAY_AI_API_KEY in .env'}

    try:
        response_text = scaleway_client.vision_completion(
            image_data=image_path_or_bytes,
            prompt=INVOICE_EXTRACTION_PROMPT,
            model=scaleway_client.MODELS['vision'],
            temperature=0.1,
            max_tokens=2048,
        )

        # Try to parse JSON from response
        # The model might wrap it in ```json ... ```
        clean_text = response_text.strip()
        if clean_text.startswith('```'):
            # Remove markdown code block
            lines = clean_text.split('\n')
            clean_text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        data = json.loads(clean_text)

        # Validate and clean the data
        return _clean_extracted_data(data)

    except json.JSONDecodeError as e:
        logger.error(f'Failed to parse AI response as JSON: {e}')
        logger.error(f'Raw response: {response_text[:500]}')
        return {'error': f'Could not parse AI response: {str(e)}', 'raw_response': response_text}
    except Exception as e:
        logger.error(f'Invoice OCR error: {e}')
        return {'error': str(e)}


def _clean_extracted_data(data):
    """Validate and clean extracted invoice data."""
    cleaned = {
        'supplier_name': data.get('supplier_name') or '',
        'invoice_number': data.get('invoice_number') or '',
        'date': data.get('date') or '',
        'items': [],
        'subtotal': _to_decimal(data.get('subtotal')),
        'tax_amount': _to_decimal(data.get('tax_amount')),
        'total_amount': _to_decimal(data.get('total_amount')),
        'notes': data.get('notes') or '',
    }

    for item in data.get('items', []):
        cleaned_item = {
            'description': item.get('description', ''),
            'reference': item.get('reference') or '',
            'weight': _to_decimal(item.get('weight')),
            'quantity': item.get('quantity', 1) or 1,
            'unit_price': _to_decimal(item.get('unit_price')),
            'total_price': _to_decimal(item.get('total_price')),
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
