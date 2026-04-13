import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0009_catalogtoken_user'),
        ('settings_app', '0006_jewelrytype'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='jewelry_type',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='settings_app.jewelrytype',
                verbose_name='Type de bijou',
            ),
        ),
    ]
