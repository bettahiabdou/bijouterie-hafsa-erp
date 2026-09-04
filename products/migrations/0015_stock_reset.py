from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0014_product_blocks'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='status',
            field=models.CharField(
                choices=[
                    ('available', 'Disponible'),
                    ('reserved', 'Réservé'),
                    ('sold', 'Vendu'),
                    ('in_repair', 'En réparation'),
                    ('consigned_in', 'En consignation (reçu)'),
                    ('consigned_out', 'En consignation (prêté)'),
                    ('returned', 'Retourné'),
                    ('custom_order', 'Commande sur mesure'),
                    ('inactive', 'Désactivé'),
                ],
                default='available',
                max_length=20,
                verbose_name='Statut',
            ),
        ),
        migrations.AddField(
            model_name='stockcountsession',
            name='deactivated_products',
            field=models.ManyToManyField(
                blank=True,
                related_name='+',
                to='products.product',
                verbose_name='Produits désactivés (réinitialisation)',
            ),
        ),
    ]
