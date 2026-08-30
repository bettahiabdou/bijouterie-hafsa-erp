from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sales', '0019_salestarget'),
    ]

    operations = [
        migrations.CreateModel(
            name='AmanaStatement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.CharField(db_index=True, help_text='Format AAAA-MM, ex: 2026-06', max_length=7, verbose_name='Mois')),
                ('original_filename', models.CharField(blank=True, max_length=255, verbose_name='Nom du fichier')),
                ('file', models.FileField(blank=True, null=True, upload_to='amana_statements/', verbose_name='Fichier')),
                ('sha256', models.CharField(db_index=True, max_length=64, unique=True, verbose_name='Empreinte')),
                ('line_count', models.PositiveIntegerField(default=0, verbose_name='Nombre de lignes')),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Total encaissé')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, verbose_name='Importé le')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='amana_statements', to=settings.AUTH_USER_MODEL, verbose_name='Importé par')),
            ],
            options={
                'verbose_name': 'Relevé AMANA',
                'verbose_name_plural': 'Relevés AMANA',
                'ordering': ['-month', '-uploaded_at'],
            },
        ),
        migrations.CreateModel(
            name='AmanaStatementLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation_date', models.CharField(blank=True, max_length=10, verbose_name='Date opération')),
                ('value_date', models.CharField(blank=True, max_length=10, verbose_name='Date valeur')),
                ('tracking_ref', models.CharField(db_index=True, max_length=40, verbose_name='Référence colis')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Montant')),
                ('statement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='sales.amanastatement', verbose_name='Relevé')),
            ],
            options={
                'verbose_name': 'Ligne de relevé AMANA',
                'verbose_name_plural': 'Lignes de relevé AMANA',
                'ordering': ['statement', 'operation_date'],
                'indexes': [models.Index(fields=['tracking_ref'], name='sales_amana_trackin_ad779e_idx')],
            },
        ),
    ]
