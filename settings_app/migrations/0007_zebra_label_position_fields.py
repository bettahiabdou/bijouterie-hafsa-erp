from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0006_jewelrytype'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_x_mm',
            field=models.PositiveIntegerField(
                default=32,
                help_text='Décalage horizontal du texte depuis le bord gauche',
                verbose_name='Position X texte (mm)',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_weight_y_mm',
            field=models.PositiveIntegerField(
                default=17,
                help_text='Position verticale du poids et pureté',
                verbose_name='Position Y poids (mm)',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_size_y_mm',
            field=models.PositiveIntegerField(
                default=20,
                help_text='Position verticale de la taille (T: XXcm)',
                verbose_name='Position Y taille (mm)',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_ref_y_mm',
            field=models.PositiveIntegerField(
                default=23,
                help_text='Position verticale de la référence',
                verbose_name='Position Y référence (mm)',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_label_barcode_y_mm',
            field=models.PositiveIntegerField(
                default=31,
                help_text='Position verticale du code-barres',
                verbose_name='Position Y code-barres (mm)',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_rfid_enabled',
            field=models.BooleanField(
                default=True,
                help_text="Encoder le tag RFID lors de l'impression",
                verbose_name='Encodage RFID activé',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_rfid_position',
            field=models.PositiveIntegerField(
                default=240,
                help_text='Position de programmation RFID en dots (PROG. POSITION)',
                verbose_name='Position RFID (dots)',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_rfid_retries',
            field=models.PositiveIntegerField(
                default=10,
                help_text="Nombre de tentatives en cas d'échec d'encodage",
                verbose_name='Tentatives RFID',
            ),
        ),
        migrations.AddField(
            model_name='systemconfig',
            name='zebra_rfid_bank',
            field=models.PositiveIntegerField(
                default=2,
                help_text='Banque mémoire RFID (1=Reserved, 2=EPC, 3=TID, 4=User)',
                verbose_name='Banque mémoire RFID',
            ),
        ),
    ]
