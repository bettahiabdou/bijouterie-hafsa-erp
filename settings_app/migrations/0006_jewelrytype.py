from django.db import migrations, models


def seed_jewelry_types(apps, schema_editor):
    JewelryType = apps.get_model('settings_app', 'JewelryType')
    types = [
        ('Bague mariage', 'JT-BAG'),
        ('Sertla beldi', 'JT-SER'),
        ('Bracelet mekherem', 'JT-BMK'),
        ('Bracelet Moderne', 'JT-BMO'),
        ('Radcou cou', 'JT-RCO'),
        ('Radcou Main', 'JT-RMA'),
        ('Bague moderne', 'JT-BGM'),
        ('Bague beldi', 'JT-BGB'),
        ('Boucles beldi', 'JT-BOB'),
        ('Boucle moderne', 'JT-BOM'),
        ('Chaîne promo', 'JT-CHP'),
    ]
    for name, code in types:
        JewelryType.objects.get_or_create(name=name, defaults={'code': code})


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0005_merge_20260212_2012'),
    ]

    operations = [
        migrations.CreateModel(
            name='JewelryType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Nom')),
                ('name_ar', models.CharField(blank=True, max_length=100, verbose_name='Nom (Arabe)')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='Code')),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
            ],
            options={
                'verbose_name': 'Type de bijou',
                'verbose_name_plural': 'Types de bijoux',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(seed_jewelry_types, migrations.RunPython.noop),
    ]
