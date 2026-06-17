from django.db import migrations, models


# Methods that are real cash-in-hand at sale time (NOT collected later by a carrier)
STANDARD_CASH_METHODS = {
    'espèces', 'especes', 'virement bancaire', 'carte de crédit', 'carte de credit',
    'carte de débit', 'carte de debit', 'chèque', 'cheque', 'paiement mobile',
    'dépôt client', 'depot client', 'achat or +espèce', 'achat or +espece',
}


def seed_carrier_flag(apps, schema_editor):
    PaymentMethod = apps.get_model('settings_app', 'PaymentMethod')
    for pm in PaymentMethod.objects.all():
        name = (pm.name or '').strip().lower()
        # Anything that isn't a standard cash method is treated as collected by
        # the carrier/AMANA (contre-remboursement) by default. Adjustable in config.
        if name not in STANDARD_CASH_METHODS:
            pm.collected_by_carrier = True
            pm.save(update_fields=['collected_by_carrier'])


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0007_zebra_label_position_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentmethod',
            name='collected_by_carrier',
            field=models.BooleanField(
                default=False,
                help_text='Le montant est à encaisser par le livreur (contre-remboursement), pas encore reçu en caisse',
                verbose_name='Encaissé par le transporteur / AMANA',
            ),
        ),
        migrations.RunPython(seed_carrier_flag, migrations.RunPython.noop),
    ]
