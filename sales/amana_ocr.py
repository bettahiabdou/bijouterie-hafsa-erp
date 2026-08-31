"""
OCR for scanned (image) BaridBank statements.

Scanned statements have no text layer, so we render each page with PyMuPDF and
read it with Tesseract. OCR is imperfect on scans, so we make the result
reliable by leaning on data we trust:

  * References are read with word-level confidence, the two printed copies per
    row are voted against each other, coerced toward the QB<9 digits>MA shape,
    and snapped to the closest real AMANA delivery tracking number.
  * Amounts are the weakest thing OCR reads, so whenever a row's ref matches a
    delivery we take the amount from that delivery's expected COD instead of the
    scan. OCR amounts are only a fallback for rows with no matching delivery.

The remaining uncertain rows are shown for the user to correct before import.

Requires: pymupdf, pytesseract (pip) and the tesseract-ocr binary (apt/brew).
"""
import re
import difflib
from decimal import Decimal, InvalidOperation

_REF_STRICT = re.compile(r'[A-Z]{2}\d{9}MA')
_REF_LOOSE = re.compile(r'[A-Z0-9]{2}\d{5,}[A-Z0-9]{2}')
_DATE_RE = re.compile(r'\d{2}/\d{2}/\d{4}')
_AMT_RE = re.compile(r'\d[\d  ]*[.,]\d{2}')

# OCR look-alikes for forcing the 9 middle characters to digits / the ends to letters
_TO_DIGIT = str.maketrans({'O': '0', 'Q': '0', 'D': '0', 'I': '1', 'L': '1', 'l': '1',
                           'Z': '2', 'S': '5', 'G': '6', 'T': '7', 'B': '8', 'g': '9'})


def ocr_pages(data_bytes, dpi=450):
    """Render every page and return a list of pytesseract DICT results."""
    import pymupdf
    import pytesseract
    from PIL import Image
    import io
    out = []
    doc = pymupdf.open(stream=data_bytes, filetype='pdf')
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = Image.open(io.BytesIO(pix.tobytes('png')))
        out.append(pytesseract.image_to_data(
            img, lang='eng', config='--psm 6',
            output_type=pytesseract.Output.DICT))
    return out


def _clean_amount(raw):
    s = str(raw).replace(' ', '').replace(' ', '')
    if re.match(r'^\d+,\d{2}$', s):
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _coerce_ref(tok):
    """Force an OCR token toward the QB<9 digits>MA shape when it's close."""
    s = re.sub(r'[^A-Za-z0-9]', '', str(tok)).upper()
    if len(s) != 13:
        return s
    head = s[:2].replace('8', 'B').replace('0', 'Q').replace('5', 'S')
    mid = s[2:11].translate(_TO_DIGIT)
    tail = s[11:].replace('8', 'B').replace('0', 'O').replace('1', 'A')  # ...MA
    cand = head + mid + tail
    return cand if _REF_STRICT.fullmatch(cand) else s


def _lines(dict_result):
    """Reconstruct OCR lines: list of {tokens:[(text,conf)], text, top}."""
    d = dict_result
    grouped = {}
    for i in range(len(d['text'])):
        t = (d['text'][i] or '').strip()
        c = int(d['conf'][i])
        if not t or c < 0:
            continue
        key = (d['block_num'][i], d['par_num'][i], d['line_num'][i])
        grouped.setdefault(key, {'tokens': [], 'top': d['top'][i]})
        grouped[key]['tokens'].append((t, c))
    lines = []
    for key in sorted(grouped, key=lambda k: grouped[k]['top']):
        g = grouped[key]
        lines.append({'tokens': g['tokens'], 'text': ' '.join(t for t, _ in g['tokens']),
                      'top': g['top']})
    return lines


def _best_ref(candidates):
    """candidates: list of (token, conf). Return the best QB…MA guess."""
    scored = []
    for tok, conf in candidates:
        coerced = _coerce_ref(tok)
        bonus = 40 if _REF_STRICT.fullmatch(coerced) else 0
        scored.append((conf + bonus, coerced))
    if not scored:
        return ''
    scored.sort(reverse=True)
    return scored[0][1]


def parse_ocr_rows(data_bytes):
    """
    Extract candidate COD rows from a scanned statement.
    Returns list of {date, raw_ref, amount}.
    """
    rows = []
    for dr in ocr_pages(data_bytes):
        lines = _lines(dr)
        for idx, ln in enumerate(lines):
            if 'REMBOURS' not in ln['text'].upper():
                continue
            # ref candidates: this line's ref-like tokens + a following line that
            # is essentially just a ref (the wrapped "Réf. Titre" copy).
            cands = [(t, c) for (t, c) in ln['tokens']
                     if _REF_LOOSE.fullmatch(re.sub(r'[^A-Za-z0-9]', '', t))]
            for j in (idx + 1, idx + 2):
                if j < len(lines):
                    nxt = lines[j]
                    if 'REMBOURS' in nxt['text'].upper():
                        break
                    for (t, c) in nxt['tokens']:
                        if _REF_LOOSE.fullmatch(re.sub(r'[^A-Za-z0-9]', '', t)):
                            cands.append((t, c))
            ref = _best_ref(cands)
            dm = _DATE_RE.search(ln['text'])
            amts = _AMT_RE.findall(ln['text'])
            amount = _clean_amount(amts[-1]) if amts else Decimal('0')
            rows.append({'date': dm.group(0) if dm else '', 'raw_ref': ref, 'amount': amount})
    return rows


AI_PROMPT = """Tu lis un relevé bancaire marocain scanné (BaridBank / Al Barid Bank).

Extrais UNIQUEMENT les lignes de type « CONTRE REMBOURSEMENT » (VERSEMENT ou
VIREMENT) qui portent un numéro de suivi de colis au format 2 lettres + chiffres
+ « MA » (par ex. QB249644531MA), visible dans la colonne « Réf. Titre » ou dans
le libellé de l'opération.

Pour chaque ligne concernée, donne :
- "date"   : la date de l'opération (JJ/MM/AAAA)
- "ref"    : le numéro de suivi EXACT (ex : QB249644531MA). Lis chaque caractère
             avec le plus grand soin, ne devine pas.
- "amount" : le montant de la colonne CRÉDIT en dirhams (nombre, ex : 1600.00)

Ignore les retraits par carte, les virements sans numéro de suivi, les frais et
le solde.

Réponds UNIQUEMENT avec un objet JSON de cette forme, sans aucun texte autour :
{"rows": [{"date": "JJ/MM/AAAA", "ref": "QB...MA", "amount": 0}]}
"""


def _parse_ai_json(text):
    import json
    clean = (text or '').strip()
    if clean.startswith('```'):
        lines = clean.split('\n')
        clean = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    items = None
    try:
        data = json.loads(clean)
        items = data.get('rows', data) if isinstance(data, dict) else data
    except (ValueError, TypeError):
        # The output was likely truncated at the token limit -> the whole array
        # won't parse. Salvage every COMPLETE {…} row object instead of losing
        # the entire page.
        items = []
        for m in re.finditer(r'\{[^{}]*\}', clean):
            try:
                items.append(json.loads(m.group(0)))
            except (ValueError, TypeError):
                continue
    out = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        ref = re.sub(r'[^A-Za-z0-9]', '', str(it.get('ref', ''))).upper()
        if not ref:
            continue
        out.append({'date': str(it.get('date', '')), 'raw_ref': ref,
                    'amount': _clean_amount(str(it.get('amount', '0')))})
    return out


def ai_extract_rows(data_bytes, dpi=200, model=None):
    """
    Read a scanned statement with the Scaleway vision model (much more accurate
    than Tesseract). Returns the same row dicts as parse_ocr_rows, or None if the
    AI service isn't configured (so the caller can fall back to Tesseract).
    """
    import os
    from ai_services import scaleway_client
    if not scaleway_client.is_configured():
        return None
    # Default to the larger vision model (Qwen-VL based, far better at dense
    # document text than pixtral). Override with the AMANA_OCR_MODEL env var,
    # e.g. "mistral-medium-3.5-128b".
    if model is None:
        model = (os.getenv('AMANA_OCR_MODEL')
                 or scaleway_client.MODELS.get('vision_large')
                 or scaleway_client.MODELS['vision'])
    import pymupdf
    import io
    from PIL import Image
    MAX_SIDE = 1800  # small vision models degenerate on oversized images
    rows = []
    doc = pymupdf.open(stream=data_bytes, filetype='pdf')
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        # The vision client tags data URIs as JPEG, so send JPEG bytes.
        img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        if max(img.size) > MAX_SIDE:
            ratio = MAX_SIDE / max(img.size)
            img = img.resize((max(1, int(img.width * ratio)),
                              max(1, int(img.height * ratio))))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        jpg = buf.getvalue()
        resp = scaleway_client.vision_completion(
            image_data=jpg,
            prompt=AI_PROMPT,
            model=model,
            temperature=0.0,
            max_tokens=8000,
            response_format={'type': 'json_object'},
        )
        rows.extend(_parse_ai_json(resp))
    # A tracking ref = one payment. Collapse duplicates (and any model repetition)
    # by keeping the first occurrence of each ref.
    seen, uniq = set(), []
    for r in rows:
        k = r.get('raw_ref') or ''
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        uniq.append(r)
    return uniq


def refine_rows(rows, delivery_cod):
    """
    Match each OCR ref to a known delivery. Only an EXACT match is trusted (and
    then the amount comes from that delivery's COD, since OCR amounts are weak).

    Fuzzy "close" deliveries are NEVER auto-applied: these tracking numbers are
    sequential, so a near neighbour is a different real parcel. A close delivery
    is offered as a non-binding suggestion in the note for the user to confirm.

    delivery_cod: dict {tracking_ref_upper_nospace: Decimal expected_cod}.
    Each returned row: {date, ref, raw_ref, amount, ocr_amount, suggestion, status, note}.
    """
    def _close_amount(a, b):
        # equal or close: within 5% of the expected amount (min 2 DH)
        tol = max(Decimal('2'), (b or Decimal('0')) * Decimal('0.05'))
        return abs((a or Decimal('0')) - (b or Decimal('0'))) <= tol

    known = list(delivery_cod.keys())
    out = []
    for r in rows:
        raw = (r['raw_ref'] or '').upper()
        ocr_amt = r['amount']
        ref, status, note, amount, suggestion = raw, 'uncertain', '', ocr_amt, ''
        if raw and raw in delivery_cod:
            expected = delivery_cod[raw]
            if expected > 0:
                if _close_amount(ocr_amt, expected):
                    # ref matches AND amount agrees -> trusted, use the exact
                    # expected amount from our data.
                    status, note, amount = 'matched', 'Livraison trouvée — montant OK', expected
                else:
                    # ref matches but the amount read doesn't match what we expect
                    # to collect -> verify (OCR slip, or a different parcel).
                    status = 'uncertain'
                    note = f'⚠️ Montant lu {ocr_amt} ≠ encaissement attendu {expected} — à vérifier'
                    amount = ocr_amt
            else:
                # ref matches but we have no expected COD to check against.
                status, note = 'matched', 'Livraison trouvée (montant non vérifiable)'
        elif raw:
            close = difflib.get_close_matches(raw, known, n=1, cutoff=0.9)
            if close and _close_amount(ocr_amt, delivery_cod.get(close[0], Decimal('0'))):
                suggestion = close[0]
                note = f'À vérifier — proche de {close[0]}, montant concordant ({delivery_cod[close[0]]})'
            elif close:
                suggestion = close[0]
                note = f'À vérifier — proche de la livraison {close[0]} ?'
            elif _REF_STRICT.fullmatch(raw):
                note = 'Format OK, aucune livraison exacte — à vérifier sur le papier'
            else:
                note = 'Référence à vérifier sur le papier'
        else:
            note = 'Référence non lue — à saisir'
        out.append({
            'date': r.get('date', ''),
            'ref': ref,
            'raw_ref': raw,
            'amount': str(amount),
            'ocr_amount': str(ocr_amt),
            'suggestion': suggestion,
            'status': status,
            'note': note,
        })
    return out
