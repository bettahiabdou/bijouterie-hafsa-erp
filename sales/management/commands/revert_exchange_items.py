"""
Revert wrongly-exchanged (traded-in) items on an invoice.

When the reprise/exchange selector traded in more items than intended, this
undoes the extra ones: the item is un-returned, its product goes back to 'sold',
its exchange action is removed, and the linked new sale's trade-in credit is
reduced accordingly (which raises that sale's balance due).

Dry-run by default. Add --apply to actually write the changes.

    python manage.py revert_exchange_items 9763-9764-9765 --keep PRD-FIN-20260826-0036
    python manage.py revert_exchange_items 9763-9764-9765 --keep PRD-FIN-20260826-0036 --apply
"""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sales.models import SaleInvoice, SaleInvoiceAction


class Command(BaseCommand):
    help = "Revert wrongly-exchanged items on an invoice (keep only the chosen refs exchanged)."

    def add_arguments(self, parser):
        parser.add_argument('invoice_ref')
        parser.add_argument('--keep', default='',
                            help='Comma-separated product refs to KEEP exchanged. All other '
                                 'currently-returned items are reverted.')
        parser.add_argument('--apply', action='store_true', help='Actually write the changes.')

    def handle(self, *args, **opts):
        ref = opts['invoice_ref']
        keep = {r.strip() for r in opts['keep'].split(',') if r.strip()}
        apply = opts['apply']

        try:
            invoice = SaleInvoice.objects.get(reference=ref, is_deleted=False)
        except SaleInvoice.DoesNotExist:
            raise CommandError(f"Invoice {ref} not found.")

        self.stdout.write(f"\nInvoice {invoice.reference}  status={invoice.status}  "
                          f"total={invoice.total_amount}  paid={invoice.amount_paid}")
        self.stdout.write(f"Keep exchanged: {sorted(keep) or '(none)'}")
        self.stdout.write("-" * 70)

        to_revert = []
        for item in invoice.items.select_related('product').all():
            pref = item.product.reference if item.product else '(no product)'
            flag = 'RETOURNÉ' if item.is_returned else 'ok'
            self.stdout.write(f"  item#{item.id}  {pref}  {flag}")
            if item.is_returned and pref not in keep:
                actions = list(SaleInvoiceAction.objects.filter(
                    original_invoice=invoice,
                    action_type=SaleInvoiceAction.ActionType.EXCHANGE,
                    original_product=item.product,
                ).select_related('new_invoice'))
                to_revert.append((item, actions))

        if not to_revert:
            self.stdout.write(self.style.WARNING("\nNothing to revert."))
            return

        self.stdout.write("\nPLANNED REVERTS:")
        for item, actions in to_revert:
            pref = item.product.reference if item.product else '(no product)'
            self.stdout.write(f"  - un-return {pref}, product -> 'sold'")
            for a in actions:
                ni = a.new_invoice
                if ni:
                    new_paid = (ni.amount_paid or Decimal('0')) - (a.refund_amount or Decimal('0'))
                    self.stdout.write(
                        f"      credit {a.refund_amount} on new sale {ni.reference}: "
                        f"paid {ni.amount_paid} -> {new_paid} "
                        f"(balance {ni.balance_due} -> {ni.total_amount - new_paid})  "
                        f"** customer now owes {a.refund_amount} more on {ni.reference} **")
                self.stdout.write(f"      delete exchange action #{a.id}")

        if not apply:
            self.stdout.write(self.style.WARNING(
                "\nDRY-RUN. Re-run with --apply to write these changes."))
            return

        with transaction.atomic():
            # Accumulate the credit to remove per new-sale, then apply once, so
            # multiple reverted items on the same new sale don't clobber each
            # other via stale cached instances.
            credit_to_remove = {}
            for item, actions in to_revert:
                for a in actions:
                    if a.new_invoice_id:
                        credit_to_remove[a.new_invoice_id] = (
                            credit_to_remove.get(a.new_invoice_id, Decimal('0'))
                            + (a.refund_amount or Decimal('0'))
                        )
                    a.delete()
                item.is_returned = False
                item.returned_at = None
                item.save(update_fields=['is_returned', 'returned_at'])
                if item.product:
                    item.product.status = 'sold'
                    item.product.save(update_fields=['status'])

            for ni_id, removed in credit_to_remove.items():
                ni = SaleInvoice.objects.get(pk=ni_id)
                ni.amount_paid = (ni.amount_paid or Decimal('0')) - removed
                if ni.amount_paid < 0:
                    ni.amount_paid = Decimal('0')
                ni.balance_due = (ni.total_amount or Decimal('0')) - ni.amount_paid
                if ni.amount_paid >= (ni.total_amount or Decimal('0')):
                    ni.status = SaleInvoice.Status.PAID
                elif ni.amount_paid > 0:
                    ni.status = SaleInvoice.Status.PARTIAL_PAID
                else:
                    ni.status = SaleInvoice.Status.UNPAID
                ni.save(update_fields=['amount_paid', 'balance_due', 'status'])

            # Recompute the invoice's own status: EXCHANGED only if every item is
            # still returned; otherwise restore from its payment state.
            invoice.refresh_from_db()
            all_returned = not invoice.items.filter(is_returned=False).exists()
            if all_returned:
                invoice.status = SaleInvoice.Status.EXCHANGED
            elif (invoice.amount_paid or Decimal('0')) >= (invoice.total_amount or Decimal('0')):
                invoice.status = SaleInvoice.Status.PAID
            elif (invoice.amount_paid or Decimal('0')) > 0:
                invoice.status = SaleInvoice.Status.PARTIAL_PAID
            else:
                invoice.status = SaleInvoice.Status.UNPAID
            invoice.save(update_fields=['status'])

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {invoice.reference} is now status={invoice.status}. "
            f"Verify the new-sale balances printed above."))
