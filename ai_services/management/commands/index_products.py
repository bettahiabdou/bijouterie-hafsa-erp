"""
Management command to index all products for semantic search.
Usage: python manage.py index_products [--all]
"""

from django.core.management.base import BaseCommand
from ai_services.embeddings import index_all_products


class Command(BaseCommand):
    help = 'Index all products for AI-powered semantic search'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Index ALL products (not just available ones)',
        )

    def handle(self, *args, **options):
        status_filter = None if options['all'] else 'available'
        status_label = 'all' if options['all'] else 'available'

        self.stdout.write(f'Indexing {status_label} products...')

        count = index_all_products(status_filter=status_filter)

        if count > 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully indexed {count} products'))
        else:
            self.stdout.write(self.style.WARNING('No products were indexed'))
