"""
Backfill rfid_tag for all products that were printed with RFID encoding
but never had the hex EPC saved to the database.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from products.models import Product
from products.print_utils import string_to_hex


class Command(BaseCommand):
    help = 'Backfill rfid_tag field for products missing it'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        products_missing = Product.objects.filter(
            Q(rfid_tag__isnull=True) | Q(rfid_tag='')
        ).exclude(
            Q(reference__isnull=True) | Q(reference='')
        )

        total = products_missing.count()
        self.stdout.write(f'Found {total} products without rfid_tag')

        updated = 0
        for product in products_missing.iterator():
            rfid_hex = string_to_hex(product.reference)
            if dry_run:
                self.stdout.write(f'  {product.reference} -> {rfid_hex}')
            else:
                Product.objects.filter(pk=product.pk).update(rfid_tag=rfid_hex)
            updated += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f'Dry run: {updated} products would be updated'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Updated {updated} products with rfid_tag'))
