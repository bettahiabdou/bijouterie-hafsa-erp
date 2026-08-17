from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0018_circulation_seller_to_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='SalesTarget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revenue_target', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Objectif CA mensuel (DH)')),
                ('margin_target', models.DecimalField(decimal_places=1, default=18, max_digits=5, verbose_name='Objectif marge (%)')),
                ('new_clients_target', models.PositiveIntegerField(default=0, verbose_name='Objectif nouveaux clients / mois')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Modifié le')),
            ],
            options={
                'verbose_name': 'Objectif commercial',
                'verbose_name_plural': 'Objectifs commerciaux',
                'ordering': ['-updated_at'],
            },
        ),
    ]
