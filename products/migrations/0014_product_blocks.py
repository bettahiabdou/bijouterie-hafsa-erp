from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0013_stock_count'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Nom du bloc')),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Modifié le')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_blocks', to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
                ('products', models.ManyToManyField(blank=True, related_name='blocks', to='products.product', verbose_name='Produits')),
            ],
            options={
                'verbose_name': 'Bloc',
                'verbose_name_plural': 'Blocs',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='stockcountsession',
            name='mode',
            field=models.CharField(choices=[('full', 'Magasin complet'), ('block_check', 'Contrôle de bloc(s)'), ('block_define', 'Définir un bloc')], default='full', max_length=20, verbose_name='Mode'),
        ),
        migrations.AddField(
            model_name='stockcountsession',
            name='blocks',
            field=models.ManyToManyField(blank=True, related_name='sessions', to='products.productblock', verbose_name='Blocs'),
        ),
        migrations.AddField(
            model_name='stockcountsession',
            name='absorbed_products',
            field=models.ManyToManyField(blank=True, related_name='+', to='products.product', verbose_name='Produits ajoutés au bloc'),
        ),
    ]
