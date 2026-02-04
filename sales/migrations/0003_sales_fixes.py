# Generated migration for critical sales fixes
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_initial'),
        ('settings_app', '0001_initial'),
        ('payments', '0001_initial'),
        ('quotes', '0001_initial'),
    ]

    operations = [
        # Add quantity field to SaleInvoiceItem
        migrations.AddField(
            model_name='saleinvoiceitem',
            name='quantity',
            field=models.DecimalField(
                decimal_places=3,
                default=1,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0.001'))],
                help_text='Quantité de produits vendus',
                verbose_name='Quantité'
            ),
        ),

        # Add tax fields to SaleInvoice
        migrations.AddField(
            model_name='saleinvoice',
            name='tax_rate',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                help_text='Taux de TVA en pourcentage',
                verbose_name='Taux TVA (%)'
            ),
        ),
        migrations.AddField(
            model_name='saleinvoice',
            name='tax_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name='Montant TVA'
            ),
        ),

        # Add payment method to SaleInvoice
        migrations.AddField(
            model_name='saleinvoice',
            name='payment_method',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sale_invoices',
                to='settings_app.paymentmethod',
                verbose_name='Méthode de paiement'
            ),
        ),

        # Add bank account to SaleInvoice
        migrations.AddField(
            model_name='saleinvoice',
            name='bank_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sale_invoices',
                to='settings_app.bankaccount',
                verbose_name='Compte bancaire'
            ),
        ),

        # Add applied deposit to SaleInvoice
        migrations.AddField(
            model_name='saleinvoice',
            name='applied_deposit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='applied_to_sales',
                to='payments.deposit',
                verbose_name='Acompte appliqué'
            ),
        ),

        # Add quote link to SaleInvoice
        migrations.AddField(
            model_name='saleinvoice',
            name='quote',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='converted_sales',
                to='quotes.quote',
                verbose_name='Devis original'
            ),
        ),
    ]
