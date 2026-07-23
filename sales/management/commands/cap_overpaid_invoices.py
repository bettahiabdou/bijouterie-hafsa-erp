"""
Audit / correct invoices whose recorded amount_paid exceeds their total.

Over-payment has SEVERAL distinct causes, and they must not be lumped together:

  arrondi         surplus < 1 DH — cents from price/gram maths. Safe to cap.
  reprise>total   trade-in worth more than the new item; the surplus was handed
                  back to the customer. Safe to cap (this is invoice 23464).
  double-comptage amount_paid is exactly 2x the real ClientPayment total — the
                  known double-count bug (ClientPayment.save() auto-increments
                  amount_paid AND a view added it again). Capping is usually
                  right, but verify.
  incoherent      amount_paid cannot be explained by real payments + exchange
                  credit at all (corrupt value). DO NOT cap blindly — inspect
                  with:  python manage.py invoice_origin <reference>
  sur-paiement    amount_paid matches payments+credit but exceeds the total
                  (genuine over-tender / change given).

Read-only by default. Use --apply to write, and narrow with --cause /
--max-surplus so each group is handled deliberately.

Usage:
    python manage.py cap_overpaid_invoices --classify
    python manage.py cap_overpaid_invoices --classify --cause incoherent
    python manage.py cap_overpaid_invoices --cause arrondi --apply
    python manage.py cap_overpaid_invoices --max-surplus 1 --apply
    python manage.py cap_overpaid_invoices 23464 --apply
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from sales.models import SaleInvoice
from payments.models import ClientPayment

CENT = Decimal('0.01')
CAUSES = ['arrondi', 'reprise>total', 'double-comptage', 'incoherent', 'sur-paiement']


def classify(inv):
    """Return (cause, payments_sum, credit_sum, surplus)."""
    total = inv.total_amount or Decimal('0')
    paid = inv.amount_paid or Decimal('0')
    surplus = paid - total

    payments_sum = ClientPayment.objects.filter(sale_invoice=inv).aggregate(
        t=Sum('amount'))['t'] or Decimal('0')
    credit_sum = inv.exchange_from.filter(action_type='exchange').aggregate(
        t=Sum('refund_amount'))['t'] or Decimal('0')
    expected = payments_sum + credit_sum

    if surplus < Decimal('1'):
        cause = 'arrondi'
    elif payments_sum > 0 and abs(paid - (payments_sum * 2)) <= CENT:
        cause = 'double-comptage'
    elif credit_sum > 0 and abs(expected - paid) <= CENT:
        cause = 'reprise>total'
    elif abs(expected - paid) > CENT:
        cause = 'incoherent'
    else:
        cause = 'sur-paiement'
    return cause, payments_sum, credit_sum, surplus


class Command(BaseCommand):
    help = "Audit/correct invoices where amount_paid exceeds the total (classified by cause)."

    def add_arguments(self, parser):
        parser.add_argument('reference', nargs='?', help="Limit to one invoice reference")
        parser.add_argument('--apply', action='store_true', help="Write changes (default: dry-run)")
        parser.add_argument('--classify', action='store_true', help="Show cause breakdown")
        parser.add_argument('--cause', choices=CAUSES, help="Limit to one cause")
        parser.add_argument('--max-surplus', type=str, help="Limit to surplus <= this amount")

    def handle(self, *args, **options):
        apply = options['apply']
        ref = options.get('reference')
        want_cause = options.get('cause')
        max_surplus = Decimal(options['max_surplus']) if options.get('max_surplus') else None

        qs = SaleInvoice.objects.filter(is_deleted=False)
        if ref:
            qs = qs.filter(reference=ref)
            if not qs.exists():
                raise CommandError(f"Aucune facture référence « {ref} ».")

        rows = []
        for inv in qs.iterator():
            if (inv.amount_paid or 0) <= (inv.total_amount or 0):
                continue
            cause, pay_sum, credit_sum, surplus = classify(inv)
            if want_cause and cause != want_cause:
                continue
            if max_surplus is not None and surplus > max_surplus:
                continue
            rows.append((inv, cause, pay_sum, credit_sum, surplus))

        if not rows:
            self.stdout.write(self.style.SUCCESS("Aucune facture correspondante."))
            return

        # --- Summary by cause ---
        summary = {}
        for _, cause, _, _, surplus in rows:
            e = summary.setdefault(cause, {'n': 0, 'sum': Decimal('0')})
            e['n'] += 1
            e['sum'] += surplus

        self.stdout.write("=" * 96)
        self.stdout.write(f"{len(rows)} facture(s) avec montant payé > total")
        self.stdout.write("=" * 96)
        self.stdout.write("RÉPARTITION PAR CAUSE :")
        for cause in CAUSES:
            if cause in summary:
                e = summary[cause]
                self.stdout.write(f"   {cause:<16} {e['n']:>4} facture(s)   surplus total {e['sum']:>14} DH")
        self.stdout.write("-" * 96)

        # --- Detail ---
        if options['classify'] or ref or apply:
            self.stdout.write(f"{'CAUSE':<16} {'FACTURE':<22} {'PAYÉ':>13} {'TOTAL':>13} {'SURPLUS':>12}")
            self.stdout.write("-" * 96)
            for inv, cause, pay_sum, credit_sum, surplus in sorted(rows, key=lambda r: -r[4]):
                line = (f"{cause:<16} {inv.reference:<22} {inv.amount_paid:>13} "
                        f"{inv.total_amount:>13} {surplus:>12}")
                if cause == 'incoherent':
                    self.stdout.write(self.style.ERROR(line))
                else:
                    self.stdout.write(line)
            self.stdout.write("-" * 96)

        if 'incoherent' in summary and not want_cause:
            self.stdout.write(self.style.ERROR(
                f"⚠ {summary['incoherent']['n']} facture(s) INCOHÉRENTE(S) : le montant payé ne "
                "correspond ni aux paiements réels ni au crédit d'échange.\n"
                "  Ne les corrigez pas en masse — inspectez-les d'abord :\n"
                "     python manage.py invoice_origin <référence>"
            ))

        if not apply:
            self.stdout.write(self.style.WARNING(
                f"\nSimulation : {len(rows)} facture(s) seraient corrigée(s). "
                "Ajoutez --apply (et de préférence --cause / --max-surplus) pour appliquer."
            ))
            return

        # --- Apply ---
        changed = 0
        for inv, cause, _, _, surplus in rows:
            old_paid = inv.amount_paid
            inv.amount_paid = inv.total_amount
            inv.balance_due = Decimal('0')
            if inv.status not in ('draft', 'cancelled', 'returned'):
                inv.status = 'paid'
            inv.save(update_fields=['amount_paid', 'balance_due', 'status'])
            changed += 1
            self.stdout.write(self.style.SUCCESS(
                f"  CORRIGÉ [{cause}] {inv.reference}: payé {old_paid} -> {inv.total_amount} "
                f"(surplus {surplus})"
            ))
        self.stdout.write(self.style.SUCCESS(f"\nTerminé : {changed} facture(s) corrigée(s)."))
