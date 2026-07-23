from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0009_productnature'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_font_size',
            field=models.PositiveIntegerField(default=24, verbose_name='Taille police (dots)'),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_barcode_height',
            field=models.PositiveIntegerField(default=55, verbose_name='Hauteur code-barres (dots)'),
        ),
    ]
