# Generated migration for adding payment_reference field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0005_optional_client'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleinvoice',
            name='payment_reference',
            field=models.CharField(
                blank=True,
                help_text='N° de chèque, référence virement, n° de carte, etc.',
                max_length=100,
                null=True,
                unique=True,
                verbose_name='Référence de paiement'
            ),
        ),
    ]
