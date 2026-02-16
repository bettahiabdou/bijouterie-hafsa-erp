"""
Fix double-counted payment totals on invoices.

The ClientPayment.save() auto-increments invoice.amount_paid via update_payment(),
but some views also manually added the payment amount, causing double-counting.

This command recalculates amount_paid from actual ClientPayment records.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum
from sales.models import SaleInvoice
from payments.models import ClientPayment


class Command(BaseCommand):
    help = 'Recalculate invoice amount_paid from actual ClientPayment records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fixed = 0
        errors = 0

        invoices = SaleInvoice.objects.exclude(status='draft').exclude(is_deleted=True)
        self.stdout.write(f'Checking {invoices.count()} invoices...')

        for invoice in invoices:
            actual_paid = ClientPayment.objects.filter(
                sale_invoice=invoice
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            if invoice.amount_paid != actual_paid:
                old_paid = invoice.amount_paid
                old_balance = invoice.balance_due
                old_status = invoice.status

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  {invoice.reference}: amount_paid {old_paid} -> {actual_paid} '
                            f'(diff: {old_paid - actual_paid})'
                        )
                    )
                else:
                    invoice.amount_paid = actual_paid
                    invoice.balance_due = invoice.total_amount - actual_paid

                    if actual_paid >= invoice.total_amount:
                        invoice.status = 'paid'
                        invoice.balance_due = Decimal('0')
                    elif actual_paid > 0:
                        invoice.status = 'partial'
                        invoice.balance_due = invoice.total_amount - actual_paid
                    else:
                        invoice.status = 'unpaid'
                        invoice.balance_due = invoice.total_amount

                    try:
                        invoice.save(update_fields=['amount_paid', 'balance_due', 'status'])
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  FIXED {invoice.reference}: '
                                f'paid {old_paid} -> {actual_paid}, '
                                f'balance {old_balance} -> {invoice.balance_due}, '
                                f'status {old_status} -> {invoice.status}'
                            )
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'  ERROR {invoice.reference}: {e}')
                        )
                        errors += 1
                        continue

                fixed += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDry run: {fixed} invoices would be fixed'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nDone: {fixed} invoices fixed, {errors} errors'))
