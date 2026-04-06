import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('products', '0006_product_ai_image_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='CatalogToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(max_length=64, unique=True, verbose_name='Token')),
                ('name', models.CharField(help_text='Ex: Equipe en ligne Casablanca', max_length=100, verbose_name='Nom')),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Créé par')),
            ],
            options={
                'verbose_name': 'Token catalogue',
                'verbose_name_plural': 'Tokens catalogue',
            },
        ),
    ]
