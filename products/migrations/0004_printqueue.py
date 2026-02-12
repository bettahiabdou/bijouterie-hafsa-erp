# Generated manually for PrintQueue model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0003_product_bank_account'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrintQueue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label_type', models.CharField(choices=[('product', 'Etiquette produit'), ('price', 'Etiquette prix'), ('test', 'Test')], default='product', max_length=20, verbose_name="Type d'etiquette")),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Quantite')),
                ('zpl_data', models.TextField(help_text="Commandes ZPL brutes a envoyer a l'imprimante", verbose_name='Donnees ZPL')),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('printing', 'En cours'), ('printed', 'Imprime'), ('failed', 'Echec'), ('cancelled', 'Annule')], default='pending', max_length=20, verbose_name='Statut')),
                ('error_message', models.TextField(blank=True, verbose_name="Message d'erreur")),
                ('attempts', models.PositiveIntegerField(default=0, verbose_name='Tentatives')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Cree le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Modifie le')),
                ('printed_at', models.DateTimeField(blank=True, null=True, verbose_name='Imprime le')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='print_jobs', to=settings.AUTH_USER_MODEL, verbose_name='Cree par')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='print_jobs', to='products.product', verbose_name='Produit')),
            ],
            options={
                'verbose_name': "File d'impression",
                'verbose_name_plural': "File d'impression",
                'ordering': ['-created_at'],
            },
        ),
    ]
