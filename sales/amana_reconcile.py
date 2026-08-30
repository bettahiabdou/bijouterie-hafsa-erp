"""
AMANA statement reconciliation helpers.

Standalone tool: parse an uploaded bank statement PDF (Relevé des Opérations),
extract the 'VERSEMENT CONTRE REMBOURSEMENT QB…MA' credit lines, and match the
tracking numbers against AMANA deliveries. Read-only: never modifies deliveries.
"""
import re
from decimal import Decimal, InvalidOperation

# One credit line carries a parcel tracking number (QBxxxxxxxxMA) and the amount
# AMANA remitted for it. Lump 'VIREMENT ... PAR UN CENTRE' lines carry no
# reference and are intentionally ignored.
_LABEL = 'VERSEMENT CONTRE REMBOURSEMENT'
_DATE_RE = re.compile(r'\d{2}/\d{2}/\d{2}')
_REF_RE = re.compile(r'QB\w+MA')
_AMT_RE = re.compile(r'[\d  ]*\d[.,]\d{2}')


def _clean_amount(raw):
    """Turn a French/EN money token ('5 950.00', '1 000,00') into a Decimal."""
    s = raw.replace(' ', '').replace(' ', '')
    # comma as decimal separator (e.g. 1000,00) -> dot; otherwise drop thousands commas
    if re.match(r'^\d+,\d{2}$', s):
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def extract_text(file_obj):
    """Extract all text from a PDF file object using pdfplumber."""
    import pdfplumber
    text = ''
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or '') + '\n'
    return text


def parse_statement_lines(text):
    """
    Return a list of {operation_date, value_date, tracking_ref, amount} for every
    'VERSEMENT CONTRE REMBOURSEMENT QB…MA' line found in the statement text.
    Line-based and layout-tolerant.
    """
    out = []
    for line in text.split('\n'):
        if _LABEL not in line:
            continue
        ref_m = _REF_RE.search(line)
        if not ref_m:
            continue  # unreferenced (PAR UN CENTRE etc.) -> ignore
        dates = _DATE_RE.findall(line)
        amts = _AMT_RE.findall(line)
        amount = _clean_amount(amts[-1]) if amts else Decimal('0')
        out.append({
            'operation_date': dates[0] if dates else '',
            'value_date': dates[1] if len(dates) > 1 else '',
            'tracking_ref': ref_m.group(0).upper(),
            'amount': amount,
        })
    return out


def normalize_ref(ref):
    """Normalize a tracking number for matching (uppercase, no spaces)."""
    return (ref or '').upper().replace(' ', '').strip()
