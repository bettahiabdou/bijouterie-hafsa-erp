# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0001_initial'),
        ('sales', '0007_invoicephoto_and_more'),
    ]

    operations = [
        # Add new status choices to SaleInvoice
        migrations.AlterField(
            model_name='saleinvoice',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Brouillon'),
                    ('unpaid', 'Non payée'),
                    ('partial', 'Partiellement payée'),
                    ('paid', 'Payée'),
                    ('cancelled', 'Annulée'),
                    ('returned', 'Retournée'),
                    ('exchanged', 'Échangée'),
                ],
                default='unpaid',
                max_length=20,
                verbose_name='Statut'
            ),
        ),
        # Create SaleInvoiceAction model
        migrations.CreateModel(
            name='SaleInvoiceAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('return', 'Retour'), ('exchange', 'Échange')], max_length=20, verbose_name="Type d'action")),
                ('original_product_ref', models.CharField(blank=True, max_length=100, verbose_name='Référence produit original')),
                ('refund_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Montant remboursé')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
                ('new_invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exchange_from', to='sales.saleinvoice', verbose_name='Nouvelle facture')),
                ('original_invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='sales.saleinvoice', verbose_name='Facture originale')),
                ('original_product', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sale_returns', to='products.product', verbose_name='Produit original')),
                ('replacement_product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sale_replacements', to='products.product', verbose_name='Produit de remplacement')),
            ],
            options={
                'verbose_name': 'Action facture vente',
                'verbose_name_plural': 'Actions facture vente',
                'ordering': ['-created_at'],
            },
        ),
    ]
