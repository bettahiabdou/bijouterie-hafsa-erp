from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('purchases', '0003_purchaseinvoiceaction'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseInvoicePhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='purchase_invoice_photos/%Y/%m/%d/', verbose_name='Image')),
                ('caption', models.TextField(blank=True, verbose_name='Légende')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, verbose_name='Téléchargé le')),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='purchases.purchaseinvoice', verbose_name='Facture')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Téléchargé par')),
            ],
            options={
                'verbose_name': 'Photo facture achat',
                'verbose_name_plural': 'Photos factures achat',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
