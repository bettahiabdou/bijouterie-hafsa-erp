from django.db import migrations, models


def seed_product_natures(apps, schema_editor):
    ProductNature = apps.get_model('settings_app', 'ProductNature')
    natures = [
        ('Rafinity', 'NAT-RAF'),
        ('Beldi', 'NAT-BEL'),
        ('Laser', 'NAT-LAS'),
    ]
    for name, code in natures:
        ProductNature.objects.get_or_create(name=name, defaults={'code': code})


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0008_paymentmethod_collected_by_carrier'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductNature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Nom')),
                ('name_ar', models.CharField(blank=True, max_length=100, verbose_name='Nom (Arabe)')),
                ('code', models.CharField(blank=True, max_length=20, unique=True, verbose_name='Code')),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
            ],
            options={
                'verbose_name': 'Nature de produit',
                'verbose_name_plural': 'Natures de produits',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(seed_product_natures, migrations.RunPython.noop),
    ]
