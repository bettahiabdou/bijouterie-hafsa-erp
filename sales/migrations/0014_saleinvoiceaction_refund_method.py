import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0013_delivery_stock_pickup'),
        ('clients', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleinvoiceaction',
            name='refund_method',
            field=models.CharField(
                choices=[('none', 'Aucun'), ('cash', 'Espèce / Remboursement'), ('deposit', 'Crédit dépôt client')],
                default='cash',
                max_length=10,
                verbose_name='Mode de remboursement',
            ),
        ),
        migrations.AddField(
            model_name='saleinvoiceaction',
            name='deposit_client',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='return_deposit_credits',
                to='clients.client',
                verbose_name='Client crédité (dépôt)',
            ),
        ),
    ]
