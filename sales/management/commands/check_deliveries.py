"""
Management command to check AMANA delivery statuses.

Run this periodically via cron to keep delivery tracking up to date.

Usage:
    python manage.py check_deliveries          # Check all pending/in-transit AMANA deliveries
    python manage.py check_deliveries --all    # Check all AMANA deliveries including delivered
    python manage.py check_deliveries --dry-run  # Show what would be checked without updating

Cron example (every 30 minutes):
    */30 * * * * cd /path/to/project && /path/to/venv/bin/python manage.py check_deliveries >> /var/log/delivery_check.log 2>&1
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from sales.models import Delivery
from sales.services import AmanaTracker


class Command(BaseCommand):
    help = 'Check AMANA delivery tracking statuses and update database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Check all AMANA deliveries, including those marked as delivered',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be checked without making any updates',
        )
        parser.add_argument(
            '--tracking',
            type=str,
            help='Check a specific tracking number only',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of deliveries to check (default: 50)',
        )

    def handle(self, *args, **options):
        check_all = options['all']
        dry_run = options['dry_run']
        specific_tracking = options['tracking']
        limit = options['limit']

        start_time = timezone.now()
        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(f"AMANA Delivery Check - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"{'=' * 60}\n")

        # Build queryset
        if specific_tracking:
            deliveries = Delivery.objects.filter(
                tracking_number=specific_tracking,
                delivery_method_type='amana'
            )
        elif check_all:
            deliveries = Delivery.objects.filter(
                delivery_method_type='amana'
            ).exclude(tracking_number='')
        else:
            # Default: only pending and in_transit
            deliveries = Delivery.objects.filter(
                delivery_method_type='amana',
                status__in=['pending', 'in_transit']
            ).exclude(tracking_number='')

        deliveries = deliveries.order_by('last_checked_at')[:limit]

        total = deliveries.count()
        self.stdout.write(f"Found {total} deliveries to check")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("\nNo deliveries to check. All done!"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] Would check the following deliveries:\n"))
            for d in deliveries:
                self.stdout.write(f"  - {d.reference}: {d.tracking_number} ({d.status})")
            return

        # Initialize tracker
        tracker = AmanaTracker()

        # Process deliveries
        stats = {
            'total': total,
            'updated': 0,
            'failed': 0,
            'status_changed': 0,
            'errors': []
        }

        for i, delivery in enumerate(deliveries, 1):
            self.stdout.write(f"\n[{i}/{total}] Checking {delivery.reference} ({delivery.tracking_number})...")

            old_status = delivery.status

            try:
                success = tracker.update_delivery(delivery)

                if success:
                    stats['updated'] += 1
                    delivery.refresh_from_db()

                    if delivery.status != old_status:
                        stats['status_changed'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  Status changed: {old_status} -> {delivery.status}")
                        )
                    else:
                        self.stdout.write(f"  Status: {delivery.status} (unchanged)")

                    if delivery.current_position:
                        self.stdout.write(f"  Position: {delivery.current_position}")
                else:
                    stats['failed'] += 1
                    self.stdout.write(self.style.WARNING(f"  Failed to get tracking info"))

            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append(f"{delivery.tracking_number}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"  Error: {str(e)}"))

        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()

        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write("SUMMARY")
        self.stdout.write(f"{'=' * 60}")
        self.stdout.write(f"Total checked:      {stats['total']}")
        self.stdout.write(f"Successfully updated: {stats['updated']}")
        self.stdout.write(f"Status changed:     {stats['status_changed']}")
        self.stdout.write(f"Failed:             {stats['failed']}")
        self.stdout.write(f"Duration:           {duration:.1f} seconds")
        self.stdout.write(f"{'=' * 60}\n")

        if stats['errors']:
            self.stdout.write(self.style.ERROR("\nErrors encountered:"))
            for error in stats['errors'][:10]:
                self.stdout.write(f"  - {error}")
            if len(stats['errors']) > 10:
                self.stdout.write(f"  ... and {len(stats['errors']) - 10} more")

        if stats['failed'] == 0:
            self.stdout.write(self.style.SUCCESS("\nAll deliveries checked successfully!"))
        elif stats['updated'] > 0:
            self.stdout.write(self.style.WARNING(f"\n{stats['updated']} updated, {stats['failed']} failed"))
        else:
            self.stdout.write(self.style.ERROR("\nNo deliveries could be updated"))
