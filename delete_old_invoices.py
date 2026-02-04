import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from sales.models import SaleInvoice

# Delete invoices with old status values
old_statuses = ['draft', 'confirmed', 'delivered', 'cancelled']
total_deleted = 0

for status in old_statuses:
    count = SaleInvoice.objects.filter(status=status).count()
    if count > 0:
        SaleInvoice.objects.filter(status=status).delete()
        print(f"✓ Deleted {count} invoices with status '{status}'")
        total_deleted += count

print(f"\nTotal deleted: {total_deleted} invoices")

# Show remaining
from django.db.models import Count
remaining = SaleInvoice.objects.values('status').annotate(count=Count('id')).order_by('status')
print("\nRemaining invoices by status:")
for item in remaining:
    status_val = item['status']
    count = item['count']
    if status_val == 'unpaid':
        label = 'Non payée'
    elif status_val == 'partial':
        label = 'Partiellement payée'
    elif status_val == 'paid':
        label = 'Payée'
    else:
        label = status_val
    print(f"  {status_val} ({label}): {count}")
