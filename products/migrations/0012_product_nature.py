import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0011_productvideo'),
        ('settings_app', '0009_productnature'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='nature',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='settings_app.productnature',
                verbose_name='Nature produit',
            ),
        ),
    ]
