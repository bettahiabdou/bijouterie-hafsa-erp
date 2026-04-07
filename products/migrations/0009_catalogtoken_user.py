from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('products', '0008_catalogtoken_password_and_logs'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogtoken',
            name='user',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='catalog_token',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Utilisateur système',
            ),
        ),
        migrations.AlterField(
            model_name='catalogtoken',
            name='name',
            field=models.CharField(
                blank=True,
                help_text="Auto-rempli depuis l'utilisateur système",
                max_length=100,
                verbose_name="Nom de l'utilisateur",
            ),
        ),
    ]
