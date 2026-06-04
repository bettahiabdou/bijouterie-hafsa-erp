import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0006_jewelrytype'),
        ('stock_storage', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockstorageitem',
            name='pickup_method',
            field=models.CharField(
                choices=[('magasin', 'Magasin (Retrait)'), ('amana', 'AMANA'), ('transporteur', 'Autre Transporteur')],
                default='magasin',
                max_length=20,
                verbose_name='Mode de récupération',
            ),
        ),
        migrations.AddField(
            model_name='stockstorageitem',
            name='carrier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stock_storage_items',
                to='settings_app.carrier',
                verbose_name='Transporteur',
            ),
        ),
        migrations.AddField(
            model_name='stockstorageitem',
            name='tracking_number',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Numéro de suivi'),
            preserve_default=False,
        ),
    ]
