# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0001_initial'),
        ('purchases', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseInvoiceAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('return', 'Retour'), ('exchange', 'Échange')], max_length=20, verbose_name="Type d'action")),
                ('original_product_ref', models.CharField(blank=True, max_length=100, verbose_name='Référence produit original')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='purchases.purchaseinvoice', verbose_name='Facture')),
                ('original_product', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_returns', to='products.product', verbose_name='Produit original')),
                ('replacement_product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_replacements', to='products.product', verbose_name='Produit de remplacement')),
            ],
            options={
                'verbose_name': 'Action facture achat',
                'verbose_name_plural': 'Actions facture achat',
                'ordering': ['-created_at'],
            },
        ),
    ]
