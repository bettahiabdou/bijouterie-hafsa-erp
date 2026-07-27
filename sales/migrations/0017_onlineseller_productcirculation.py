import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0012_product_nature'),
        ('sales', '0016_delivery_repair'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OnlineSeller',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Nom')),
                ('phone', models.CharField(blank=True, max_length=30, verbose_name='Téléphone')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
            ],
            options={
                'verbose_name': 'Vendeuse en ligne',
                'verbose_name_plural': 'Vendeuses en ligne',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ProductCirculation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('out', 'En circulation'), ('sold', 'Vendu'), ('returned', 'Retour vitrine')], db_index=True, default='out', max_length=20, verbose_name='Statut')),
                ('date_out', models.DateTimeField(auto_now_add=True, verbose_name='Date de sortie')),
                ('date_back', models.DateTimeField(blank=True, null=True, verbose_name='Date de retour/vente')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='circulations', to='sales.saleinvoice', verbose_name='Facture')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='circulations', to='products.product', verbose_name='Produit')),
                ('returned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='circulations_returned', to=settings.AUTH_USER_MODEL, verbose_name='Retour saisi par')),
                ('seller', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='circulations', to='sales.onlineseller', verbose_name='Vendeuse')),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='circulations_sent', to=settings.AUTH_USER_MODEL, verbose_name='Sortie par')),
            ],
            options={
                'verbose_name': 'Circulation produit',
                'verbose_name_plural': 'Circulations produits',
                'ordering': ['-date_out'],
                'indexes': [models.Index(fields=['status', 'product'], name='sales_produ_status_e1d439_idx')],
            },
        ),
    ]
