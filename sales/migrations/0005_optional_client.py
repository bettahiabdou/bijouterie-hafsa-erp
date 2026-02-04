# Generated migration for optional client field
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0004_phase3_business_logic'),
        ('clients', '0001_initial'),
    ]

    operations = [
        # Make client field optional (nullable)
        migrations.AlterField(
            model_name='saleinvoice',
            name='client',
            field=models.ForeignKey(
                blank=True,
                help_text='Client is optional - can record walk-in or anonymous sales',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sale_invoices',
                to='clients.client',
                verbose_name='Client'
            ),
        ),
    ]
