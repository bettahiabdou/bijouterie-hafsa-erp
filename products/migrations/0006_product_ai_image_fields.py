from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0005_alter_printqueue_created_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='ai_image_status',
            field=models.CharField(
                choices=[
                    ('pending', 'En attente'),
                    ('processing', 'En cours'),
                    ('completed', 'Terminé'),
                    ('failed', 'Échoué'),
                    ('skipped', 'Ignoré'),
                ],
                default='pending',
                max_length=20,
                verbose_name='Statut image IA',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='ai_image_error',
            field=models.TextField(blank=True, null=True, verbose_name='Erreur image IA'),
        ),
        migrations.AddField(
            model_name='product',
            name='ai_image_attempts',
            field=models.PositiveIntegerField(default=0, verbose_name='Tentatives image IA'),
        ),
        migrations.AddField(
            model_name='product',
            name='ai_image_completed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Image IA générée le'),
        ),
    ]
