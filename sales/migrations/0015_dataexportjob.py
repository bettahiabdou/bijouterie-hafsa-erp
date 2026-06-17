import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0014_saleinvoiceaction_refund_method'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DataExportJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('running', 'En cours'), ('done', 'Terminé'), ('failed', 'Échoué')], default='pending', max_length=10, verbose_name='Statut')),
                ('file', models.FileField(blank=True, null=True, upload_to='exports/', verbose_name='Fichier')),
                ('error', models.TextField(blank=True, verbose_name='Erreur')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='Terminé le')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='data_export_jobs', to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
            ],
            options={
                'verbose_name': 'Export de données',
                'verbose_name_plural': 'Exports de données',
                'ordering': ['-created_at'],
            },
        ),
    ]
