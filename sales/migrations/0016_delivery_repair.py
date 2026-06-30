import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0015_dataexportjob'),
        ('repairs', '0002_repair_weight_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='delivery',
            name='repair',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='deliveries',
                to='repairs.repair',
                verbose_name='Réparation',
            ),
        ),
    ]
