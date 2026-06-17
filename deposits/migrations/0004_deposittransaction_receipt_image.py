from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deposits', '0003_depositaccount_managed_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='deposittransaction',
            name='receipt_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='deposits/receipts/',
                verbose_name='Reçu (preuve de paiement)',
            ),
        ),
    ]
