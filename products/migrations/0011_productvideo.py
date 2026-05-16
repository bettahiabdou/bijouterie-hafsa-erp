import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0010_product_jewelry_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductVideo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('video', models.FileField(upload_to='products/videos/', verbose_name='Vidéo')),
                ('poster', models.ImageField(blank=True, null=True, upload_to='products/videos/posters/', verbose_name='Image de couverture')),
                ('display_order', models.PositiveIntegerField(default=0, verbose_name='Ordre')),
                ('duration_seconds', models.PositiveIntegerField(blank=True, null=True, verbose_name='Durée (s)')),
                ('file_size_bytes', models.PositiveBigIntegerField(blank=True, null=True, verbose_name='Taille (octets)')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_product_videos', to=settings.AUTH_USER_MODEL, verbose_name='Téléversé par')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='videos', to='products.product', verbose_name='Produit')),
            ],
            options={
                'verbose_name': 'Vidéo produit',
                'verbose_name_plural': 'Vidéos produit',
                'ordering': ['display_order', 'created_at'],
            },
        ),
    ]
