"""
Diagnose why scanned RFID tags don't match products.

Analyzes the scanned EPCs of a saved inventory session (tap "Sauvegarder
session" on the handheld first) and classifies each one:

  matched          resolves to a product (exact or PC-offset) — fine
  decodable-hit    the EPC decodes to text that matches a product reference,
                   but its rfid_tag didn't match -> encoding/DB mismatch (FIXABLE)
  decodable-miss   decodes to clean text but no product has that reference
                   (old/deleted item, or a foreign labelled tag)
  garbled          the EPC isn't valid/that decodes to junk -> read error, or a
                   non-shop tag (metal jewelry causes many partial reads)

Usage:
    python manage.py rfid_diagnose                 # latest session
    python manage.py rfid_diagnose --session 42
    python manage.py rfid_diagnose --samples 15    # show more example EPCs
"""
import string
from django.core.management.base import BaseCommand, CommandError
from products.models import Product, RFIDInventorySession


PRINTABLE = set(string.printable) - set('\t\n\r\x0b\x0c')


def decode_epc(epc):
    """Hex EPC -> best-effort ASCII text, or None if not decodable/clean."""
    e = (epc or '').strip()
    if len(e) % 2:  # odd length -> not valid hex bytes
        e = e[:-1]
    try:
        text = bytes.fromhex(e).decode('latin-1')
    except ValueError:
        return None
    text = text.strip('\x00').strip()
    if not text or any(c not in PRINTABLE for c in text):
        return None
    return text


class Command(BaseCommand):
    help = "Classify why scanned RFID tags did/didn't match products."

    def add_arguments(self, parser):
        parser.add_argument('--session', type=int, help="Session id (default: latest)")
        parser.add_argument('--samples', type=int, default=10, help="Example EPCs per category")

    def handle(self, *args, **options):
        if options.get('session'):
            try:
                session = RFIDInventorySession.objects.get(pk=options['session'])
            except RFIDInventorySession.DoesNotExist:
                raise CommandError(f"Session {options['session']} introuvable.")
        else:
            session = RFIDInventorySession.objects.order_by('-started_at').first()
            if not session:
                raise CommandError("Aucune session enregistrée. Tapez 'Sauvegarder session' d'abord.")

        tags = session.scanned_tags or []
        epcs = [t.get('epc', '').strip().upper() for t in tags if isinstance(t, dict) and t.get('epc')]
        epcs = [e for e in epcs if e]
        self.stdout.write(f"Session #{session.id} — {len(epcs)} tags scannés\n" + "=" * 60)

        # Build the same maps the matcher uses
        db_tags = set(
            t.upper() for t in Product.objects.exclude(rfid_tag='').exclude(rfid_tag__isnull=True)
            .values_list('rfid_tag', flat=True)
        )
        suffix_map = {t[4:]: t for t in db_tags if len(t) >= 24}

        cats = {'matched': [], 'decodable-hit': [], 'decodable-miss': [], 'garbled': []}
        for epc in epcs:
            if epc in db_tags or (len(epc) >= 20 and epc[:20] in suffix_map):
                cats['matched'].append(epc)
                continue
            text = decode_epc(epc)
            if text is None:
                cats['garbled'].append(epc)
            elif Product.objects.filter(reference__endswith=text).exists() or \
                    Product.objects.filter(reference__icontains=text).exists():
                cats['decodable-hit'].append((epc, text))
            else:
                cats['decodable-miss'].append((epc, text))

        total = len(epcs) or 1
        self.stdout.write("\nRÉPARTITION :")
        for cat in ('matched', 'decodable-hit', 'decodable-miss', 'garbled'):
            n = len(cats[cat])
            self.stdout.write(f"   {cat:<15} {n:>5}  ({100*n//total}%)")

        s = options['samples']
        if cats['decodable-hit']:
            self.stdout.write(self.style.WARNING(
                f"\n⚠ {len(cats['decodable-hit'])} tag(s) DÉCODABLES vers un produit existant "
                "mais non appariés -> problème d'encodage/rfid_tag (RÉPARABLE). Exemples :"))
            for epc, text in cats['decodable-hit'][:s]:
                p = Product.objects.filter(reference__icontains=text).first()
                self.stdout.write(f"     EPC {epc}  ->  '{text}'  ->  {p.reference if p else '?'} "
                                  f"(rfid_tag DB: {p.rfid_tag if p else '—'})")
        if cats['garbled']:
            self.stdout.write(f"\nExemples 'garbled' (lecture partielle / tag étranger) :")
            for epc in cats['garbled'][:s]:
                self.stdout.write(f"     {epc}")
        if cats['decodable-miss']:
            self.stdout.write(f"\nExemples 'decodable-miss' (texte propre, aucun produit) :")
            for epc, text in cats['decodable-miss'][:s]:
                self.stdout.write(f"     {epc}  ->  '{text}'")
        self.stdout.write("")
