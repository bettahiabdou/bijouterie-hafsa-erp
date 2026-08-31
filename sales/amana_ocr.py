"""
OCR for scanned (image) BaridBank statements.

Scanned statements have no text layer, so we render each page to an image with
PyMuPDF and read it with Tesseract, then extract the COD rows (tracking ref +
credit amount). OCR is imperfect on scans, so results are meant to be REVIEWED
and corrected by a human before import. To cut the correction work, each OCR'd
ref is snapped to the closest real AMANA delivery tracking number when it is
clearly the same one off by an OCR slip.

Requires: pymupdf, pytesseract (pip) and the tesseract-ocr binary (apt/brew).
"""
import re
import difflib
from decimal import Decimal, InvalidOperation

_REF_LOOSE = re.compile(r'[A-Z0-9]{2}\d{5,}[A-Z0-9]{2}')
_REF_STRICT = re.compile(r'[A-Z]{2}\d{9}MA')
_DATE_RE = re.compile(r'\d{2}/\d{2}/\d{4}')
_AMT_RE = re.compile(r'\d[\d  ]*[.,]\d{2}')


def ocr_pdf(data_bytes, dpi=400):
    """Render every page of a scanned PDF and OCR it. Returns the full text."""
    import pymupdf
    import pytesseract
    from PIL import Image
    import io
    text = ''
    doc = pymupdf.open(stream=data_bytes, filetype='pdf')
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = Image.open(io.BytesIO(pix.tobytes('png')))
        text += pytesseract.image_to_string(img, lang='eng', config='--psm 6') + '\n'
    return text


def _clean_amount(raw):
    s = raw.replace(' ', '').replace(' ', '')
    if re.match(r'^\d+,\d{2}$', s):
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def parse_ocr_rows(text):
    """
    Best-effort extraction of COD rows from OCR text. One dict per row:
    {date, raw_ref, amount}. Only rows mentioning a remboursement are kept.
    """
    rows = []
    for line in text.split('\n'):
        if 'REMBOURS' not in line.upper():
            continue
        compact = line.replace(' ', '')
        refs = _REF_STRICT.findall(compact) or _REF_LOOSE.findall(compact)
        raw_ref = refs[0].upper() if refs else ''
        dm = _DATE_RE.search(line)
        amts = _AMT_RE.findall(line)
        amount = _clean_amount(amts[-1]) if amts else Decimal('0')
        rows.append({'date': dm.group(0) if dm else '', 'raw_ref': raw_ref, 'amount': amount})
    return rows


def refine_rows(rows, known_refs):
    """
    Add matching/confidence info to OCR rows.
    known_refs: iterable of real AMANA delivery tracking numbers (upper, no space).
    Each row gets: ref (best guess), status ('matched' | 'corrected' | 'uncertain'),
    note, amount.
    """
    known = list({(r or '').upper().replace(' ', '') for r in known_refs if r})
    out = []
    for r in rows:
        raw = (r['raw_ref'] or '').upper()
        ref, status, note = raw, 'uncertain', ''
        if raw and raw in known:
            ref, status, note = raw, 'matched', 'Livraison trouvée'
        elif raw:
            close = difflib.get_close_matches(raw, known, n=1, cutoff=0.85)
            if close:
                ref, status = close[0], 'corrected'
                note = f'OCR « {raw} » → livraison {close[0]}'
            elif _REF_STRICT.fullmatch(raw):
                status, note = 'uncertain', 'Format OK, pas de livraison correspondante'
            else:
                status, note = 'uncertain', 'Référence à vérifier'
        else:
            note = 'Référence non lue'
        out.append({
            'date': r.get('date', ''),
            'ref': ref,
            'raw_ref': raw,
            'amount': str(r['amount']),
            'status': status,
            'note': note,
        })
    return out
