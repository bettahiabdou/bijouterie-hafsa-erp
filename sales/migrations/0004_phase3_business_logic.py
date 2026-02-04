# Generated migration for Phase 3: Business Logic
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0003_sales_fixes'),
    ]

    operations = [
        # Add soft delete field to SaleInvoice
        migrations.AddField(
            model_name='saleinvoice',
            name='is_deleted',
            field=models.BooleanField(
                default=False,
                help_text='Marqué comme supprimé (soft delete)',
                verbose_name='Supprimé'
            ),
        ),

        # Add database index for soft delete queries
        migrations.AddIndex(
            model_name='saleinvoice',
            index=models.Index(
                fields=['is_deleted', '-date'],
                name='sales_saleinvoice_is_deleted_date_idx'
            ),
        ),
    ]
