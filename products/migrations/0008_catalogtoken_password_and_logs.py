import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0007_catalogtoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogtoken',
            name='password_hash',
            field=models.CharField(blank=True, help_text='Hash PBKDF2 du mot de passe — jamais en clair', max_length=255, verbose_name='Mot de passe (hash)'),
        ),
        migrations.AddField(
            model_name='catalogtoken',
            name='last_accessed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Dernier accès'),
        ),
        migrations.AddField(
            model_name='catalogtoken',
            name='access_count',
            field=models.PositiveIntegerField(default=0, verbose_name="Nombre d'accès"),
        ),
        migrations.AlterField(
            model_name='catalogtoken',
            name='name',
            field=models.CharField(help_text='Ex: Ahmed - Equipe Casablanca', max_length=100, verbose_name="Nom de l'utilisateur"),
        ),
        migrations.AlterModelOptions(
            name='catalogtoken',
            options={'verbose_name': 'Accès catalogue', 'verbose_name_plural': 'Accès catalogue'},
        ),
        migrations.CreateModel(
            name='CatalogAccessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='Adresse IP')),
                ('user_agent', models.CharField(blank=True, max_length=500, verbose_name='User-Agent')),
                ('accessed_at', models.DateTimeField(auto_now_add=True, verbose_name='Date')),
                ('token', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_logs', to='products.catalogtoken')),
            ],
            options={
                'verbose_name': 'Accès catalogue (log)',
                'verbose_name_plural': 'Accès catalogue (logs)',
                'ordering': ['-accessed_at'],
                'indexes': [
                    models.Index(fields=['-accessed_at'], name='products_ca_accesse_idx'),
                    models.Index(fields=['token', '-accessed_at'], name='products_ca_token_a_idx'),
                ],
            },
        ),
    ]
