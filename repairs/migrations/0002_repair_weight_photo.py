from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('repairs', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='repair',
            name='weight_grams',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True, verbose_name='Poids (g)'),
        ),
        migrations.AddField(
            model_name='repair',
            name='photo',
            field=models.ImageField(blank=True, null=True, upload_to='repairs/', verbose_name='Photo du produit'),
        ),
        migrations.AlterField(
            model_name='repair',
            name='estimated_completion_date',
            field=models.DateField(blank=True, null=True, verbose_name="Date d'achèvement estimée"),
        ),
    ]
