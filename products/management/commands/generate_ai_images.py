"""
Management command to generate AI model photos for products in the background.

Usage:
    python manage.py generate_ai_images                    # Process up to 10 pending products
    python manage.py generate_ai_images --batch-size=5     # Process 5 at a time
    python manage.py generate_ai_images --dry-run          # Show what would be processed
    python manage.py generate_ai_images --retry-failed     # Also retry failed products
    python manage.py generate_ai_images --product-id=P-001 # Process a specific product

Cron (every 5 min):
    */5 * * * * cd /path/to/project && DJANGO_SETTINGS_MODULE=config.settings_production \
        flock -n /tmp/ai_images.lock venv/bin/python manage.py generate_ai_images >> /var/log/ai_images.log 2>&1
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from products.models import Product


class Command(BaseCommand):
    help = 'Generate AI model photos for products that need them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Number of products to process in parallel (default: 10)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without doing anything',
        )
        parser.add_argument(
            '--product-id',
            type=str,
            help='Process a specific product by reference',
        )
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Also retry previously failed products (max 3 attempts)',
        )

    def handle(self, *args, **options):
        from ai_services.fal_client import is_configured

        if not is_configured():
            self.stderr.write('FAL_AI_KEY not configured. Exiting.')
            return

        batch_size = options['batch_size']
        dry_run = options['dry_run']
        product_id = options['product_id']
        retry_failed = options['retry_failed']

        if product_id:
            # Process a specific product
            try:
                products = [Product.objects.get(reference=product_id)]
            except Product.DoesNotExist:
                self.stderr.write(f'Product {product_id} not found.')
                return
        else:
            # Build query for products needing AI images
            q = Q(ai_image_status=Product.AIImageStatus.PENDING)
            if retry_failed:
                q |= Q(
                    ai_image_status=Product.AIImageStatus.FAILED,
                    ai_image_attempts__lt=3,
                )

            # Only process available (active) products with at least one image
            products = list(
                Product.objects.filter(q)
                .filter(status=Product.Status.AVAILABLE)
                .filter(
                    Q(main_image__isnull=False) & ~Q(main_image='') |
                    Q(images__isnull=False)
                )
                .distinct()
                .order_by('created_at')[:batch_size]
            )

            # Mark non-available pending products as skipped
            Product.objects.filter(
                ai_image_status=Product.AIImageStatus.PENDING
            ).exclude(
                status=Product.Status.AVAILABLE
            ).update(ai_image_status=Product.AIImageStatus.SKIPPED)

            # Also mark available products with no image as skipped
            no_image_products = (
                Product.objects.filter(ai_image_status=Product.AIImageStatus.PENDING, status=Product.Status.AVAILABLE)
                .filter(Q(main_image__isnull=True) | Q(main_image=''))
                .exclude(images__isnull=False)
                .distinct()
            )
            skipped_count = no_image_products.update(ai_image_status=Product.AIImageStatus.SKIPPED)
            if skipped_count:
                self.stdout.write(f'Skipped {skipped_count} products with no images.')

        if not products:
            self.stdout.write('No products to process.')
            return

        self.stdout.write(f'Found {len(products)} products to process.')

        if dry_run:
            for p in products:
                self.stdout.write(f'  - {p.reference}: {p.name} (status={p.ai_image_status})')
            self.stdout.write('Dry run complete. No images generated.')
            return

        # Mark as processing
        product_ids = [p.id for p in products]
        Product.objects.filter(id__in=product_ids).update(
            ai_image_status=Product.AIImageStatus.PROCESSING
        )
        # Refresh objects
        for p in products:
            p.ai_image_status = Product.AIImageStatus.PROCESSING

        self.stdout.write(f'Processing {len(products)} products in parallel...')

        from products.ai_image_utils import generate_batch
        results = generate_batch(products)

        success = sum(1 for v in results.values() if not isinstance(v, Exception))
        failed = sum(1 for v in results.values() if isinstance(v, Exception))

        self.stdout.write(f'Done. Success: {success}, Failed: {failed}')

        for pid, result in results.items():
            product = next(p for p in products if p.id == pid)
            if isinstance(result, Exception):
                self.stderr.write(f'  FAIL {product.reference}: {result}')
            else:
                self.stdout.write(f'  OK   {product.reference}: {result.image.url}')
