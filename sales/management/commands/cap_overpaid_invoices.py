"""
Correct invoices whose recorded amount_paid exceeds their total.

This happens when a trade-in (reprise) is worth more than the new item: the
surplus is handed back to the customer (cash/virement) but was mistakenly kept
in amount_paid, so "Total payé" showed more than "Total". This caps amount_paid
at the invoice total, zeroes the balance, and keeps the status paid.

Read-only by default. Pass --apply to write.

Usage:
    python manage.py cap_overpaid_invoices                 # dry-run, all invoices
    python manage.py cap_overpaid_invoices 23464           # dry-run, one invoice
    python manage.py cap_overpaid_invoices 23464 --apply   # fix one invoice
    python manage.py cap_overpaid_invoices --apply         # fix all over-paid invoices
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from sales.models import SaleInvoice


class Command(BaseCommand):
    help = "Cap invoices where amount_paid exceeds the total (trade-in surplus handed back)."

    def add_arguments(self, parser):
        parser.add_argument('reference', nargs='?', help="Limit to one invoice reference")
        parser.add_argument('--apply', action='store_true', help="Write changes (default: dry-run)")

    def handle(self, *args, **options):
        apply = options['apply']
        ref = options.get('reference')

        qs = SaleInvoice.objects.filter(is_deleted=False)
        if ref:
            qs = qs.filter(reference=ref)
            if not qs.exists():
                raise CommandError(f"Aucune facture référence « {ref} ».")

        # Only those actually over-paid
        overpaid = [inv for inv in qs if (inv.amount_paid or 0) > (inv.total_amount or 0)]

        if not overpaid:
            self.stdout.write(self.style.SUCCESS("Aucune facture avec montant payé supérieur au total."))
            return

        self.stdout.write(f"{len(overpaid)} facture(s) sur-payée(s){' :' if overpaid else ''}")
        self.stdout.write("-" * 78)
        changed = 0
        for inv in overpaid:
            old_paid = inv.amount_paid
            old_balance = inv.balance_due
            surplus = old_paid - inv.total_amount
            if apply:
                inv.amount_paid = inv.total_amount
                inv.balance_due = Decimal('0')
                if inv.status not in ('draft', 'cancelled', 'returned'):
                    inv.status = 'paid'
                inv.save(update_fields=['amount_paid', 'balance_due', 'status'])
                changed += 1
                tag = self.style.SUCCESS("CORRIGÉ")
            else:
                tag = self.style.WARNING("À corriger")
            self.stdout.write(
                f"  {tag} {inv.reference}: payé {old_paid} -> {inv.total_amount} "
                f"(surplus rendu {surplus}), solde {old_balance} -> 0.00"
            )

        self.stdout.write("-" * 78)
        if apply:
            self.stdout.write(self.style.SUCCESS(f"Terminé : {changed} facture(s) corrigée(s)."))
        else:
            self.stdout.write(self.style.WARNING(
                f"Simulation : {len(overpaid)} facture(s) seraient corrigée(s). "
                "Relancez avec --apply pour appliquer."
            ))
