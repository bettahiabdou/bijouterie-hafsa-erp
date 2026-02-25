"""
Sales photo OCR using Scaleway Vision AI.
Extracts product data from photos sent by salespeople via Telegram.
Two-pass architecture: classify photo type first, then extract with focused prompt.
Handles: AMANA delivery slips, sales receipts, handwritten notes.
Supports French, Arabic (MSA), and Moroccan Darija.
"""

import json
import re
import logging
from . import scaleway_client

logger = logging.getLogger(__name__)

# --- Pass 1: Classification prompt (short, fast) ---
CLASSIFY_PROMPT = """Regarde cette photo et identifie le type de document.

Types possibles:
- "amana_slip": Bordereau AMANA / Bon de livraison Poste Maroc (formulaire imprimé avec cases, code-barres)
- "receipt": Reçu ou facture de bijouterie (papier souvent JAUNE avec liste de produits, prix, poids)
- "payment": Reçu de paiement / versement (preuve de paiement, montant payé)
- "note": Note manuscrite (informations client, commande écrite à la main)
- "other": Autre type de document

Retourne UNIQUEMENT un JSON: {"photo_type": "amana_slip|receipt|payment|note|other"}"""

# --- Pass 2: Type-specific extraction prompts ---
AMANA_PROMPT = """Tu extrais les données d'un BORDEREAU AMANA (Poste Maroc / Barid Al Maghrib).

Lis UNIQUEMENT ce qui est écrit sur CE document. NE COPIE PAS d'exemples.

Cherche sur ce formulaire:
- **Code de suivi AMANA**: code-barres avec lettres+chiffres (format: 2 lettres + chiffres + 2-3 lettres)
- **Numéro de bordereau**: nombre imprimé en haut du formulaire
- **Nom du destinataire**: champ "Destinataire" ou "المرسل إليه"
- **Téléphone**: numéro à 10 chiffres commençant par 06 ou 07
- **Montant COD**: contre-remboursement (الثمن/المبلغ), dans une case encadrée
- **Ville destination**: champ "Destination" ou "Ville"
- **Poids colis**: en kg ou g

ATTENTION: 5 ≠ S, 0 ≠ O, 1 ≠ I, 6 ≠ G

Retourne ce JSON avec les valeurs LUES sur le document:
{
    "photo_type": "amana_slip",
    "receipt_number": null,
    "client_name": "valeur lue",
    "client_phone": "valeur lue",
    "client_city": "valeur lue",
    "delivery_info": {
        "tracking_number": "valeur lue",
        "bordereau_number": "valeur lue",
        "carrier": "amana",
        "cod_amount": "valeur lue (nombre)",
        "destination": "valeur lue",
        "weight_package": "valeur lue"
    },
    "items": [],
    "total_amount": null,
    "discount_total": null,
    "payment_info": {"amount_paid": null, "payment_method": null, "reference": null},
    "notes": "autres infos utiles lues sur le document"
}

Si une information n'est pas visible, mets null. NE DEVINE PAS. NE COPIE PAS les descriptions ci-dessus comme valeurs."""

RECEIPT_PROMPT = """Tu extrais les données d'un REÇU/FACTURE DE BIJOUTERIE.

RÈGLES ABSOLUES:
- Lis UNIQUEMENT ce qui est écrit sur CE papier. NE COPIE PAS les descriptions du JSON ci-dessous comme valeurs.
- Retourne EXACTEMENT le nombre de produits écrits sur le reçu. Pas plus, pas moins.
- NE FABRIQUE PAS de données. Chaque valeur doit être lue sur le papier.

C'est un papier (souvent JAUNE) avec une liste de produits bijoux.

Cherche sur CE papier:
- **Numéro de reçu**: nombre imprimé en ROUGE sur le papier, souvent en haut. Copie TOUS les chiffres visibles.
- **Produits**: chaque ligne de produit avec sa description, poids, prix
- **Poids en grammes**: nombre décimal visible sur le reçu
- **Prix**: montant en DH visible sur le reçu
- **Remise**: réduction appliquée (si visible)
- **Total**: prix final (الباقي = reste/final)
- **Client**: nom, téléphone, ville (si mentionné)

Si le texte est en arabe, traduis en français. ATTENTION: 5 ≠ S, 0 ≠ O, 1 ≠ I, 6 ≠ G

Retourne ce JSON en remplaçant chaque "LIRE_SUR_PAPIER" par la valeur réelle lue:
{
    "photo_type": "receipt",
    "receipt_number": "LIRE_SUR_PAPIER",
    "client_name": "LIRE_SUR_PAPIER",
    "client_phone": "LIRE_SUR_PAPIER",
    "client_city": "LIRE_SUR_PAPIER",
    "delivery_info": {"tracking_number": null, "bordereau_number": null, "carrier": null, "cod_amount": null, "destination": null, "weight_package": null},
    "items": [
        {
            "description": "LIRE_SUR_PAPIER",
            "category": "LIRE_SUR_PAPIER",
            "metal_type": "LIRE_SUR_PAPIER",
            "purity": "LIRE_SUR_PAPIER",
            "weight_grams": "LIRE_SUR_PAPIER",
            "quantity": 1,
            "unit_price": "LIRE_SUR_PAPIER",
            "discount": "LIRE_SUR_PAPIER"
        }
    ],
    "total_amount": "LIRE_SUR_PAPIER",
    "discount_total": "LIRE_SUR_PAPIER",
    "payment_info": {
        "amount_paid": "LIRE_SUR_PAPIER",
        "payment_method": "LIRE_SUR_PAPIER",
        "reference": "LIRE_SUR_PAPIER"
    },
    "notes": "LIRE_SUR_PAPIER — infos CLIENT uniquement, pas l'en-tête magasin"
}

Si une information n'est pas visible sur le papier, mets null.
NE COPIE PAS "LIRE_SUR_PAPIER" comme valeur — remplace par ce que tu LIS."""

PAYMENT_PROMPT = """Tu extrais les données d'un REÇU DE PAIEMENT / VERSEMENT.

Lis UNIQUEMENT ce qui est écrit sur CE document. NE COPIE PAS d'exemples.
Ce n'est PAS un reçu de bijouterie — receipt_number doit être null.

Cherche:
- **Montant payé**: somme versée en DH
- **Mode de paiement**: espèces, chèque, virement, carte
- **Référence du paiement**: tout numéro visible → mets dans payment_info.reference
- **Nom du client**: qui a payé
- **Date**: date du paiement

Retourne ce JSON en remplaçant "LIRE_SUR_PAPIER" par les valeurs lues:
{
    "photo_type": "payment",
    "receipt_number": null,
    "client_name": "LIRE_SUR_PAPIER",
    "client_phone": "LIRE_SUR_PAPIER",
    "client_city": "LIRE_SUR_PAPIER",
    "delivery_info": {"tracking_number": null, "bordereau_number": null, "carrier": null, "cod_amount": null, "destination": null, "weight_package": null},
    "items": [],
    "total_amount": null,
    "discount_total": null,
    "payment_info": {
        "amount_paid": "LIRE_SUR_PAPIER",
        "payment_method": "LIRE_SUR_PAPIER",
        "reference": "LIRE_SUR_PAPIER"
    },
    "notes": "LIRE_SUR_PAPIER — date et détails du paiement"
}

Si une information n'est pas visible, mets null. NE COPIE PAS "LIRE_SUR_PAPIER" comme valeur."""

NOTE_PROMPT = """Tu extrais les données d'une NOTE MANUSCRITE liée à une vente de bijouterie au Maroc.

RÈGLE ABSOLUE: Extrait UNIQUEMENT ce qui est réellement écrit. NE FABRIQUE PAS de données.

Cherche toute information utile:
- Nom du client, téléphone, ville
- Produits mentionnés (UNIQUEMENT ceux écrits sur la note)
- Montants, poids en grammes
- Instructions de livraison

Si le texte est en arabe, traduis en français (ex: خاتم=bague, سلسلة=chaîne).

Retourne ce JSON:
{
    "photo_type": "note",
    "receipt_number": null,
    "client_name": "nom du client (si visible)",
    "client_phone": "téléphone (si visible)",
    "client_city": "ville (si visible)",
    "delivery_info": {"tracking_number": null, "bordereau_number": null, "carrier": null, "cod_amount": null, "destination": null, "weight_package": null},
    "items": [
        {
            "description": "description en français de CE produit lu sur la note",
            "category": "catégorie du bijou",
            "metal_type": "or|argent|plaqué_or|acier|autre",
            "purity": "18K|21K|24K|14K|9K|925",
            "weight_grams": "poids en grammes",
            "quantity": 1,
            "unit_price": "prix en DH",
            "discount": null
        }
    ],
    "total_amount": "total en DH",
    "discount_total": null,
    "payment_info": {"amount_paid": null, "payment_method": null, "reference": null},
    "notes": "autres infos utiles"
}

Si une information n'est pas visible, mets null. NE DEVINE PAS."""

# Map photo types to their extraction prompts
EXTRACTION_PROMPTS = {
    'amana_slip': AMANA_PROMPT,
    'receipt': RECEIPT_PROMPT,
    'payment': PAYMENT_PROMPT,
    'note': NOTE_PROMPT,
}


def extract_sales_data(image_path_or_bytes):
    """
    Extract structured data from a sales photo using two-pass OCR.

    Pass 1: Classify the document type (amana_slip, receipt, payment, note)
    Pass 2: Extract data using a type-specific focused prompt

    Args:
        image_path_or_bytes: File path string or image bytes

    Returns:
        dict: Extracted sales data or error dict
    """
    if not scaleway_client.is_configured():
        return {'error': 'Service IA non configuré. Configurez SCALEWAY_AI_API_KEY dans .env'}

    try:
        # --- Pass 1: Classify document type ---
        photo_type = _classify_photo(image_path_or_bytes)
        logger.info(f'Photo classified as: {photo_type}')

        # --- Pass 2: Extract with type-specific prompt ---
        extraction_prompt = EXTRACTION_PROMPTS.get(photo_type, RECEIPT_PROMPT)
        return _extract_with_prompt(image_path_or_bytes, extraction_prompt)

    except Exception as e:
        logger.error(f'Sales OCR error: {e}')
        return {'error': str(e)}


def _classify_photo(image_path_or_bytes):
    """Pass 1: Classify the photo type with a short prompt."""
    try:
        response_text = scaleway_client.vision_completion(
            image_data=image_path_or_bytes,
            prompt=CLASSIFY_PROMPT,
            model=scaleway_client.MODELS['vision'],
            temperature=0.0,
            max_tokens=64,
            response_format={"type": "json_object"},
        )

        clean_text = _extract_json_from_response(response_text)
        data = json.loads(clean_text)
        photo_type = data.get('photo_type', 'other')

        # Normalize to known types
        if photo_type in EXTRACTION_PROMPTS:
            return photo_type
        # Map common variants
        if photo_type in ('invoice', 'facture'):
            return 'receipt'
        if photo_type in ('delivery', 'bon_livraison'):
            return 'amana_slip'
        return 'receipt'  # Default to receipt (most common)

    except Exception as e:
        logger.warning(f'Photo classification failed, defaulting to receipt: {e}')
        return 'receipt'


def _extract_with_prompt(image_path_or_bytes, prompt):
    """Pass 2: Extract data using vision model.

    Uses vision_large (mistral-small-3.2-24b) if available for better OCR,
    falls back to pixtral-12b.
    """
    last_error = None
    last_raw = ''

    # Prefer larger model for extraction accuracy (pixtral-12b hallucinates on handwriting)
    model = scaleway_client.MODELS.get('vision_large', scaleway_client.MODELS['vision'])

    for attempt in range(2):
        try:
            response_text = scaleway_client.vision_completion(
                image_data=image_path_or_bytes,
                prompt=prompt,
                model=model,
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            clean_text = _extract_json_from_response(response_text)
            data = _parse_json_robust(clean_text)
            return _clean_sales_data(data)

        except json.JSONDecodeError as e:
            last_error = e
            last_raw = response_text
            logger.warning(f'JSON parse failed (attempt {attempt + 1}): {e}')
            logger.warning(f'Raw response: {response_text[:500]}')
            continue
        except Exception as e:
            logger.error(f'Sales OCR extraction error: {e}')
            return {'error': str(e)}

    logger.error(f'All JSON parse attempts failed: {last_error}')
    return {'error': 'Impossible de lire la réponse IA après 2 tentatives', 'raw_response': last_raw}


def _extract_json_from_response(text):
    """Extract JSON from AI response, handling markdown code blocks and extra text."""
    clean = text.strip()

    # Remove markdown code blocks
    if clean.startswith('```'):
        lines = clean.split('\n')
        lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        clean = '\n'.join(lines).strip()

    # If response has text before JSON, find the first {
    if clean and clean[0] != '{':
        brace_pos = clean.find('{')
        if brace_pos >= 0:
            clean = clean[brace_pos:]

    # If response has text after JSON, find the last }
    if clean:
        last_brace = clean.rfind('}')
        if last_brace >= 0:
            clean = clean[:last_brace + 1]

    return clean


def _parse_json_robust(text):
    """Parse JSON with automatic repair of common AI-generated issues."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Repair common issues
    repaired = text

    # Fix trailing commas before } or ]
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

    # Fix unescaped newlines in strings
    repaired = _fix_newlines_in_strings(repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: close unclosed structures
    repaired = _close_unclosed_json(repaired)

    return json.loads(repaired)


def _fix_newlines_in_strings(text):
    """Replace actual newlines inside JSON string values with spaces."""
    result = []
    in_string = False
    escape_next = False

    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
            continue

        if char == '\\':
            result.append(char)
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string

        if in_string and char == '\n':
            result.append(' ')
        else:
            result.append(char)

    return ''.join(result)


def _close_unclosed_json(text):
    """Try to close unclosed JSON structures."""
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')

    in_string = False
    escape_next = False
    for char in text:
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string

    result = text

    if in_string:
        result += '"'

    result += ']' * max(0, open_brackets)
    result += '}' * max(0, open_braces)

    return result


def _strip_null(value):
    """Convert literal string 'null'/'None'/'N/A'/placeholder to empty string."""
    if value is None:
        return ''
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('null', 'none', 'n/a', 'n\\a', 'nan', 'lire_sur_papier'):
            return ''
        # Also catch if model copied the placeholder with variations
        if 'lire_sur_papier' in v or 'lire sur papier' in v:
            return ''
    return value


def _clean_receipt_number(value):
    """Clean receipt number: max 15 chars, reject garbage (all zeros, repeating)."""
    raw = _strip_null((value or '')).strip()
    if not raw:
        return ''
    # Cap at 15 characters (no receipt number is longer)
    if len(raw) > 15:
        logger.warning(f'Receipt number too long ({len(raw)} chars), discarding: {raw[:20]}...')
        return ''
    # Reject all-zeros
    if raw.replace('0', '') == '':
        logger.warning(f'Receipt number is all zeros, discarding: {raw}')
        return ''
    return raw


def _clean_sales_data(data):
    """Validate and clean extracted sales data, filtering null strings."""
    delivery = data.get('delivery_info') or {}

    cleaned = {
        'photo_type': data.get('photo_type', 'other'),
        'receipt_number': _clean_receipt_number(data.get('receipt_number')),
        'client_name': _strip_null(data.get('client_name') or ''),
        'client_phone': _strip_null(data.get('client_phone') or ''),
        'client_city': _strip_null(data.get('client_city') or ''),
        'delivery_info': {
            'tracking_number': _strip_null((delivery.get('tracking_number') or '')).strip(),
            'bordereau_number': _strip_null((delivery.get('bordereau_number') or '')).strip(),
            'carrier': _strip_null(delivery.get('carrier') or ''),
            'cod_amount': _to_decimal(delivery.get('cod_amount')),
            'destination': _strip_null(delivery.get('destination') or ''),
            'weight_package': _strip_null(delivery.get('weight_package') or ''),
        },
        'items': [],
        'total_amount': _to_decimal(data.get('total_amount')),
        'discount_total': _to_decimal(data.get('discount_total')),
        'payment_info': {
            'amount_paid': _to_decimal((data.get('payment_info') or {}).get('amount_paid')),
            'payment_method': _strip_null((data.get('payment_info') or {}).get('payment_method') or ''),
            'reference': _strip_null((data.get('payment_info') or {}).get('reference') or ''),
        },
        'notes': _clean_notes(_strip_null(data.get('notes') or '')),
    }

    for item in data.get('items', []):
        cleaned_item = {
            'description': _strip_null(item.get('description', '')),
            'category': _strip_null(item.get('category', 'autre')) or 'autre',
            'metal_type': _strip_null(item.get('metal_type') or ''),
            'purity': _strip_null(item.get('purity') or ''),
            'weight': _to_decimal(item.get('weight_grams') or item.get('weight')),
            'quantity': item.get('quantity', 1) or 1,
            'unit_price': _to_decimal(item.get('unit_price')),
            'discount': _to_decimal(item.get('discount')),
        }
        cleaned['items'].append(cleaned_item)

    # Detect hallucinated items (sequential weights/prices = fabricated data)
    cleaned['items'] = _filter_hallucinated_items(cleaned['items'])

    return cleaned


def _filter_hallucinated_items(items):
    """Detect and remove hallucinated items with sequential/fabricated patterns.

    Signs of hallucination:
    - Too many items (receipts rarely have more than 6-8 items)
    - Sequential weights (e.g. 2.53, 2.46, 2.44, 2.43... decreasing by ~0.01)
    - Sequential prices (e.g. 2460, 2340, 2320... decreasing by ~20)
    - All items have nearly identical descriptions
    """
    if len(items) <= 2:
        return items  # Can't detect patterns with 1-2 items

    # Check for sequential weights
    weights = []
    for item in items:
        try:
            w = float(item.get('weight') or 0)
            if w > 0:
                weights.append(w)
        except (ValueError, TypeError):
            pass

    if len(weights) >= 4:
        # Check if weights form a near-arithmetic sequence
        diffs = [weights[i] - weights[i + 1] for i in range(len(weights) - 1)]
        if diffs:
            avg_diff = sum(abs(d) for d in diffs) / len(diffs)
            # If all differences are similar (within 0.05g) → sequential pattern
            if avg_diff > 0 and all(abs(abs(d) - avg_diff) < 0.05 for d in diffs):
                logger.warning(
                    f'Hallucination detected: {len(items)} items with sequential weights '
                    f'{weights[:5]}... (avg diff: {avg_diff:.3f}g). Clearing items.'
                )
                return []

    # Check for too many items with same description
    if len(items) >= 5:
        descriptions = [item.get('description', '') for item in items]
        most_common = max(set(descriptions), key=descriptions.count)
        if descriptions.count(most_common) >= len(items) * 0.7:
            logger.warning(
                f'Hallucination detected: {descriptions.count(most_common)}/{len(items)} '
                f'items have same description "{most_common}". Clearing items.'
            )
            return []

    return items


def _clean_notes(notes):
    """Remove store's own header info from notes (not useful)."""
    if not notes:
        return ''
    store_patterns = [
        r'Bijouterie\s+Hafsa',
        r'181\s*Av\.?\s*Ancien\s*Mellah',
        r'Patente\s*:\s*\d+',
        r'Meknes',
        r'06\s*74\s*35\s*88\s*33',
        r'06\s*63\s*76\s*38\s*42',
        r'06\s*56\s*20\s*40\s*70',
    ]
    cleaned = notes
    for pattern in store_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[,\s]*Tél\s*:\s*[,\s]*$', '', cleaned)
    cleaned = re.sub(r'\s*,\s*,\s*', ', ', cleaned)
    cleaned = re.sub(r'^\s*[,\-\s]+', '', cleaned)
    cleaned = re.sub(r'[,\-\s]+\s*$', '', cleaned)
    return cleaned.strip()


def _to_decimal(value):
    """Convert a value to a decimal string, or None. Filters placeholder strings."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('null', 'none', 'n/a', 'nan', '') or 'lire_sur_papier' in v or 'lire sur papier' in v:
            return None
    try:
        return str(round(float(value), 2))
    except (ValueError, TypeError):
        return None
