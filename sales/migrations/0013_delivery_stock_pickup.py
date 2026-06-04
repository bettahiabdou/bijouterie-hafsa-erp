import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0012_merge_20260302_1715'),
        ('stock_storage', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='delivery',
            name='invoice',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='delivery',
                to='sales.saleinvoice',
                verbose_name='Facture',
            ),
        ),
        migrations.AddField(
            model_name='delivery',
            name='stock_storage_item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='deliveries',
                to='stock_storage.stockstorageitem',
                verbose_name='Article en stock client',
            ),
        ),
    ]
