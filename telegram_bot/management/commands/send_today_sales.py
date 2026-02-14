"""
Management command to send all today's sales to admin via Telegram
Usage: python manage.py send_today_sales
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from sales.models import SaleInvoice
from telegram_bot.notifications import notify_admin_new_sale


class Command(BaseCommand):
    help = "Send all today's confirmed sales to admin via Telegram"

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Send sales for a specific date (YYYY-MM-DD). Defaults to today.',
        )

    def handle(self, *args, **options):
        if options['date']:
            from datetime import datetime
            target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
        else:
            target_date = timezone.now().date()

        # Get all non-draft, non-cancelled invoices for the target date
        invoices = SaleInvoice.objects.filter(
            date=target_date,
            is_deleted=False,
        ).exclude(
            status__in=[SaleInvoice.Status.DRAFT, SaleInvoice.Status.CANCELLED]
        ).select_related(
            'seller', 'client', 'payment_method'
        ).prefetch_related(
            'items__product', 'photos'
        ).order_by('created_at')

        count = invoices.count()

        if count == 0:
            self.stdout.write(self.style.WARNING(
                f'No confirmed sales found for {target_date.strftime("%d/%m/%Y")}'
            ))
            return

        self.stdout.write(f'Sending {count} sale(s) for {target_date.strftime("%d/%m/%Y")}...')

        sent = 0
        for invoice in invoices:
            try:
                notify_admin_new_sale(invoice)
                sent += 1
                self.stdout.write(f'  ✓ {invoice.reference}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  ✗ {invoice.reference}: {e}'
                ))

        self.stdout.write(self.style.SUCCESS(f'\nDone! Sent {sent}/{count} sales.'))
