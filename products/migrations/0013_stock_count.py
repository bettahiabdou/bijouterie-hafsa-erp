import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0012_product_nature'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StockCountSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('open', 'En cours'), ('closed', 'Terminé')], default='open', max_length=10, verbose_name='Statut')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('started_at', models.DateTimeField(auto_now_add=True, verbose_name='Démarré le')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='Terminé le')),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_counts', to=settings.AUTH_USER_MODEL, verbose_name='Démarré par')),
            ],
            options={
                'verbose_name': 'Contrôle inventaire',
                'verbose_name_plural': 'Contrôles inventaire',
                'ordering': ['-started_at'],
            },
        ),
        migrations.CreateModel(
            name='StockCountScan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=120, verbose_name='Code scanné')),
                ('scanned_at', models.DateTimeField(auto_now_add=True, verbose_name='Scanné le')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_count_scans', to='products.product', verbose_name='Produit')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scans', to='products.stockcountsession', verbose_name='Session')),
            ],
            options={
                'verbose_name': 'Scan inventaire',
                'verbose_name_plural': 'Scans inventaire',
                'ordering': ['-scanned_at'],
                'indexes': [models.Index(fields=['session', 'product'], name='products_st_session_d77228_idx')],
            },
        ),
    ]
