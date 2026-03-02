from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0010_rename_sales_saleinvoice_is_deleted_date_idx_sales_salei_is_dele_9f08b3_idx_and_more'),
    ]

    operations = [
        # 1. Drop the old unique constraint on reference
        migrations.AlterField(
            model_name='saleinvoice',
            name='reference',
            field=models.CharField(
                db_index=True,
                max_length=50,
                verbose_name='Référence',
            ),
        ),
        # 2. Add conditional unique constraint (active records only)
        migrations.AddConstraint(
            model_name='saleinvoice',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_deleted', False)),
                fields=('reference',),
                name='unique_active_invoice_reference',
            ),
        ),
    ]
