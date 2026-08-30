"""
AMANA statement reconciliation helpers.

Standalone tool: parse an uploaded bank statement PDF (Relevé des Opérations),
extract the 'VERSEMENT CONTRE REMBOURSEMENT QB…MA' credit lines, and match the
tracking numbers against AMANA deliveries. Read-only: never modifies deliveries.
"""
import re
from decimal import Decimal, InvalidOperation

# A COD credit line carries a parcel tracking number (QBxxxxxxxxMA) and the
# amount AMANA remitted for it. Banks label it differently:
#   - Bank of Africa:  "VERSEMENT CONTRE REMBOURSEMENT QB…MA"
#   - BaridBank:       "VIREMENT CONTRE REMBOURSEMENT N° QB…MA"
# We match any 'REMBOURSEMENT' line that carries a QB…MA reference, so both
# forms are caught. Lump lines with no reference (PAR UN CENTRE, BARID CASH) are
# intentionally ignored.
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
        if 'REMBOURSEMENT' not in line.upper():
            continue
        ref_m = _REF_RE.search(line)
        if not ref_m:
            continue  # unreferenced (PAR UN CENTRE, BARID CASH etc.) -> ignore
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


def parse_json_statement(data_bytes):
    """
    Parse a BaridBank (baridbanknet.ma) JSON export.
    Shape: {"operations": [{"amount": N, "date": <epoch ms>, "longLabel": "..."}]}
    Returns the same {operation_date, value_date, tracking_ref, amount} dicts as
    the PDF parser, for every credit line that carries a QB…MA reference.
    """
    import json
    import datetime
    data = json.loads(data_bytes)
    ops = data.get('operations', []) if isinstance(data, dict) else (data or [])
    out = []
    for op in ops:
        label = op.get('longLabel') or op.get('shortLabel') or ''
        if 'REMBOURSEMENT' not in label.upper():
            continue
        ref_m = _REF_RE.search(label)
        if not ref_m:
            continue
        amt = op.get('amount', 0)
        try:
            amount = Decimal(str(amt))
        except (InvalidOperation, ValueError):
            amount = Decimal('0')
        if amount <= 0:
            continue  # COD remittances are credits
        d = ''
        ts = op.get('date')
        if ts:
            try:
                d = datetime.datetime.utcfromtimestamp(int(ts) / 1000).strftime('%d/%m/%y')
            except (ValueError, OverflowError, OSError):
                d = ''
        out.append({
            'operation_date': d,
            'value_date': d,
            'tracking_ref': ref_m.group(0).upper(),
            'amount': amount,
        })
    return out


def normalize_ref(ref):
    """Normalize a tracking number for matching (uppercase, no spaces)."""
    return (ref or '').upper().replace(' ', '').strip()
