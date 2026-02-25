"""
Sales photo OCR using Scaleway Vision AI.
Extracts product data from photos sent by salespeople via Telegram.

Architecture: Describe → Structure (3 passes)
  Pass 1: Vision model classifies photo type (pixtral-12b, fast)
  Pass 2: Vision model describes what it sees in PLAIN TEXT (no JSON)
  Pass 3: Chat model (gpt-oss-120b) structures the description into JSON

This separates "reading the image" from "structuring data" — small vision
models hallucinate when asked to output JSON directly from images.
"""

import json
import re
import logging
from . import scaleway_client

logger = logging.getLogger(__name__)

# --- Pass 1: Classification ---
CLASSIFY_PROMPT = """Regarde cette photo et identifie le type de document.

Types possibles:
- "amana_slip": Bordereau AMANA / Bon de livraison Poste Maroc (formulaire imprimé avec cases, code-barres)
- "receipt": Reçu ou facture de bijouterie (papier souvent JAUNE avec liste de produits, prix, poids)
- "payment": Reçu de paiement / versement (preuve de paiement, montant payé)
- "note": Note manuscrite (informations client, commande écrite à la main)
- "other": Autre type de document

Retourne UNIQUEMENT un JSON: {"photo_type": "amana_slip|receipt|payment|note|other"}"""

# --- Pass 2: Description prompts (PLAIN TEXT, no JSON) ---
DESCRIBE_AMANA = """Décris EXACTEMENT ce que tu vois sur ce bordereau AMANA (Poste Maroc).

Lis et transcris chaque information visible:
- Le code de suivi (code-barres avec lettres et chiffres)
- Le numéro de bordereau (nombre en haut)
- Le nom du destinataire
- Le numéro de téléphone
- Le montant contre-remboursement (COD)
- La ville de destination
- Le poids du colis

Transcris les chiffres exactement: 5 ≠ S, 0 ≠ O, 1 ≠ I, 6 ≠ G.
Écris UNIQUEMENT ce que tu LIS. Si tu ne peux pas lire quelque chose, dis "illisible"."""

DESCRIBE_RECEIPT = """RÈGLE ABSOLUE: Décris UNIQUEMENT ce qui est PHYSIQUEMENT ÉCRIT sur ce papier.
Si tu ne vois pas un produit écrit, NE LE MENTIONNE PAS.
Si tu inventes un seul produit, ta réponse est FAUSSE.

Ce document est un reçu/facture de bijouterie (papier souvent JAUNE, numéro en ROUGE en haut).

Lis ligne par ligne et transcris:
1. Le numéro imprimé en rouge en haut du papier (tous les chiffres)
2. Chaque ligne de produit RÉELLEMENT ÉCRITE — description, poids (g), prix (DH)
3. Le total
4. Nom du client, téléphone, ville (si écrit)
5. Remises

COMBIEN de lignes de produits vois-tu écrites ? Indique le nombre EXACT avant de les lister.
Si tu vois 1 seule ligne, transcris 1 seul produit. Si 2 lignes, 2 produits. Pas plus.

Si le texte est en arabe, traduis en français.
Chiffres: 5 ≠ S, 0 ≠ O, 1 ≠ I, 6 ≠ G.
Si illisible, dis "illisible". N'INVENTE JAMAIS."""

DESCRIBE_PAYMENT = """Décris EXACTEMENT ce que tu vois sur ce reçu de paiement/versement.

Lis et transcris chaque information visible:
- Le montant payé
- Le mode de paiement (espèces, chèque, virement, carte)
- Tout numéro de référence visible
- Le nom du client/bénéficiaire
- La date
- Tout autre détail visible

Écris UNIQUEMENT ce que tu LIS. Si tu ne peux pas lire quelque chose, dis "illisible"."""

DESCRIBE_NOTE = """Décris EXACTEMENT ce que tu vois sur cette note manuscrite.

Lis et transcris tout ce qui est écrit:
- Noms, téléphones, villes
- Produits mentionnés avec poids et prix
- Montants
- Instructions

Si le texte est en arabe, traduis en français.
Écris UNIQUEMENT ce que tu LIS. N'INVENTE rien."""

DESCRIBE_PROMPTS = {
    'amana_slip': DESCRIBE_AMANA,
    'receipt': DESCRIBE_RECEIPT,
    'payment': DESCRIBE_PAYMENT,
    'note': DESCRIBE_NOTE,
}

# --- Pass 3: Structure prompt (chat model, text → JSON) ---
STRUCTURE_PROMPT = """Tu es un assistant qui structure des descriptions de documents de bijouterie en JSON.

On t'a donné une description textuelle d'un document. Le type du document est: {photo_type}

Voici la description du document:
---
{description}
---

Extrais les informations de cette description et retourne ce JSON:
{{
    "photo_type": "{photo_type}",
    "receipt_number": "numéro de reçu/facture (si mentionné)",
    "client_name": "nom du client (si mentionné)",
    "client_phone": "téléphone (si mentionné)",
    "client_city": "ville (si mentionné)",
    "delivery_info": {{
        "tracking_number": "code de suivi AMANA (si mentionné)",
        "bordereau_number": "numéro de bordereau (si mentionné)",
        "carrier": "amana ou null",
        "cod_amount": "montant COD en nombre (si mentionné)",
        "destination": "ville destination (si mentionné)",
        "weight_package": "poids colis (si mentionné)"
    }},
    "items": [
        {{
            "description": "description du produit en français",
            "category": "catégorie du bijou",
            "metal_type": "type de métal",
            "purity": "pureté (18K, 21K, 925, etc.)",
            "weight_grams": "poids en grammes (nombre)",
            "quantity": 1,
            "unit_price": "prix en DH (nombre)",
            "discount": "remise en DH (nombre ou null)"
        }}
    ],
    "total_amount": "total en DH (nombre ou null)",
    "discount_total": "remise totale (nombre ou null)",
    "payment_info": {{
        "amount_paid": "montant payé (nombre ou null)",
        "payment_method": "mode de paiement ou null",
        "reference": "référence de paiement ou null"
    }},
    "notes": "autres informations utiles"
}}

Règles:
- Si le type est "payment", receipt_number doit être null (les numéros vont dans payment_info.reference)
- Si le type est "amana_slip", items doit être vide []
- Si une info est marquée "illisible" ou absente, mets null
- Retourne UNIQUEMENT le JSON"""


def extract_sales_data(image_path_or_bytes):
    """
    Extract structured data from a sales photo using describe-then-structure.

    Pass 1: Classify document type (pixtral-12b)
    Pass 2: Describe what's visible in plain text (vision_large)
    Pass 3: Structure description into JSON (chat model)
    """
    if not scaleway_client.is_configured():
        return {'error': 'Service IA non configuré. Configurez SCALEWAY_AI_API_KEY dans .env'}

    try:
        # --- Pass 1: Classify ---
        photo_type = _classify_photo(image_path_or_bytes)
        logger.info(f'Photo classified as: {photo_type}')

        # --- Pass 2: Describe (vision model → plain text) ---
        description = _describe_photo(image_path_or_bytes, photo_type)
        logger.info(f'Photo description ({len(description)} chars): {description[:200]}...')

        if not description or description.strip() == '':
            return {'error': 'Le modèle n\'a pas pu lire la photo'}

        # --- Pass 3: Structure (chat model → JSON) ---
        result = _structure_description(description, photo_type)
        # Include raw description for debugging
        result['_raw_description'] = description[:500]
        return result

    except Exception as e:
        logger.error(f'Sales OCR error: {e}')
        return {'error': str(e)}


def _classify_photo(image_path_or_bytes):
    """Pass 1: Classify photo type (quick, pixtral-12b)."""
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

        if photo_type in DESCRIBE_PROMPTS:
            return photo_type
        if photo_type in ('invoice', 'facture'):
            return 'receipt'
        if photo_type in ('delivery', 'bon_livraison'):
            return 'amana_slip'
        return 'receipt'

    except Exception as e:
        logger.warning(f'Photo classification failed, defaulting to receipt: {e}')
        return 'receipt'


def _describe_photo(image_path_or_bytes, photo_type):
    """Pass 2: Vision model describes what it sees in PLAIN TEXT (no JSON).
    Falls back to pixtral-12b if vision_large returns empty or fails."""
    describe_prompt = DESCRIBE_PROMPTS.get(photo_type, DESCRIBE_RECEIPT)

    # Try vision_large first (holo2-30b-a3b)
    model_large = scaleway_client.MODELS.get('vision_large', scaleway_client.MODELS['vision'])
    model_fallback = scaleway_client.MODELS['vision']

    try:
        response_text = scaleway_client.vision_completion(
            image_data=image_path_or_bytes,
            prompt=describe_prompt,
            model=model_large,
            temperature=0.0,
            max_tokens=1024,
        )
        if response_text and response_text.strip():
            logger.info(f'vision_large ({model_large}) succeeded')
            return response_text.strip()
        logger.warning(f'vision_large ({model_large}) returned empty, falling back')
    except Exception as e:
        logger.warning(f'vision_large ({model_large}) failed: {e}, falling back')

    # Fallback to pixtral-12b
    try:
        response_text = scaleway_client.vision_completion(
            image_data=image_path_or_bytes,
            prompt=describe_prompt,
            model=model_fallback,
            temperature=0.0,
            max_tokens=1024,
        )
        logger.info(f'Fallback to {model_fallback} succeeded')
        return (response_text or '').strip()
    except Exception as e:
        logger.error(f'Fallback vision ({model_fallback}) also failed: {e}')
        return ''


def _structure_description(description, photo_type):
    """Pass 3: Chat model structures plain text into JSON."""
    prompt = STRUCTURE_PROMPT.format(
        photo_type=photo_type,
        description=description,
    )

    last_error = None
    for attempt in range(2):
        try:
            response_text = scaleway_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=scaleway_client.MODELS['chat'],
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            clean_text = _extract_json_from_response(response_text)
            data = _parse_json_robust(clean_text)
            return _clean_sales_data(data)

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f'Structure JSON parse failed (attempt {attempt + 1}): {e}')
            continue
        except Exception as e:
            logger.error(f'Structure error: {e}')
            return {'error': str(e)}

    logger.error(f'All structure attempts failed: {last_error}')
    return {'error': 'Impossible de structurer les données', 'raw_description': description}


# --- Helper functions ---

def _extract_json_from_response(text):
    """Extract JSON from AI response, handling markdown code blocks and extra text."""
    clean = text.strip()

    if clean.startswith('```'):
        lines = clean.split('\n')
        lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        clean = '\n'.join(lines).strip()

    if clean and clean[0] != '{':
        brace_pos = clean.find('{')
        if brace_pos >= 0:
            clean = clean[brace_pos:]

    if clean:
        last_brace = clean.rfind('}')
        if last_brace >= 0:
            clean = clean[:last_brace + 1]

    return clean


def _parse_json_robust(text):
    """Parse JSON with automatic repair of common AI-generated issues."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    repaired = text
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    repaired = _fix_newlines_in_strings(repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

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
        if v in ('null', 'none', 'n/a', 'n\\a', 'nan', 'lire_sur_papier', 'illisible'):
            return ''
        if 'lire_sur_papier' in v or 'lire sur papier' in v or 'illisible' in v:
            return ''
    return value


def _clean_receipt_number(value):
    """Clean receipt number: max 15 chars, reject garbage."""
    raw = _strip_null((value or '')).strip()
    if not raw:
        return ''
    if len(raw) > 15:
        logger.warning(f'Receipt number too long ({len(raw)} chars), discarding')
        return ''
    if raw.replace('0', '') == '':
        return ''
    return raw


def _clean_sales_data(data):
    """Validate and clean extracted sales data."""
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
        # Skip items with no useful data
        if cleaned_item['description'] or cleaned_item['weight'] or cleaned_item['unit_price']:
            cleaned['items'].append(cleaned_item)

    # Detect hallucinated items
    cleaned['items'] = _filter_hallucinated_items(cleaned['items'])

    return cleaned


def _filter_hallucinated_items(items):
    """Detect and remove hallucinated items with sequential/fabricated patterns."""
    if len(items) <= 1:
        return items

    weights = []
    for item in items:
        try:
            w = float(item.get('weight') or 0)
            if w > 0:
                weights.append(w)
        except (ValueError, TypeError):
            pass

    # Check sequential weights (arithmetic sequence)
    if len(weights) >= 4:
        diffs = [weights[i] - weights[i + 1] for i in range(len(weights) - 1)]
        if diffs:
            avg_diff = sum(abs(d) for d in diffs) / len(diffs)
            if avg_diff > 0 and all(abs(abs(d) - avg_diff) < 0.05 for d in diffs):
                logger.warning(f'Hallucination: sequential weights {weights[:5]}. Clearing.')
                return []

    # Check uniform price-per-gram ratio (model applying a formula)
    if len(items) >= 3:
        ratios = []
        for item in items:
            try:
                w = float(item.get('weight') or 0)
                p = float(item.get('unit_price') or 0)
                if w > 0 and p > 0:
                    ratios.append(p / w)
            except (ValueError, TypeError):
                pass
        if len(ratios) >= 3:
            avg_ratio = sum(ratios) / len(ratios)
            if avg_ratio > 0 and all(abs(r - avg_ratio) / avg_ratio < 0.05 for r in ratios):
                logger.warning(f'Hallucination: uniform price/gram {avg_ratio:.1f} DH/g across {len(ratios)} items. Clearing.')
                return []

    # Check generic category-only descriptions (no specific details)
    if len(items) >= 3:
        generic_names = {'bague', 'chaîne', 'chaine', 'bracelet', 'collier', 'pendentif',
                         'boucles', "boucles d'oreilles", 'alliance', 'chevillère', 'ensemble',
                         'corsage', 'broche', 'gourmette', 'médaille', 'medaille'}
        generic_count = 0
        for item in items:
            desc = (item.get('description') or '').strip().lower()
            # Strip metal info to check base description
            desc_base = re.sub(r'\s*(or\s*(blanc|jaune|rose)|argent|plaqué).*', '', desc).strip()
            if desc_base in generic_names:
                generic_count += 1
        if generic_count >= len(items) * 0.75:
            logger.warning(f'Hallucination: {generic_count}/{len(items)} items are bare category names. Clearing.')
            return []

    # Check repeated descriptions
    if len(items) >= 5:
        descriptions = [item.get('description', '') for item in items]
        most_common = max(set(descriptions), key=descriptions.count)
        if descriptions.count(most_common) >= len(items) * 0.7:
            logger.warning(f'Hallucination: {descriptions.count(most_common)}/{len(items)} same desc. Clearing.')
            return []

    return items


def _clean_notes(notes):
    """Remove store's own header info from notes."""
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
    """Convert a value to a decimal string, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('null', 'none', 'n/a', 'nan', '', 'illisible') or 'lire_sur_papier' in v:
            return None
    try:
        return str(round(float(value), 2))
    except (ValueError, TypeError):
        return None
