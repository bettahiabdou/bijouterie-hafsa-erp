from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deposits', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='deposittransaction',
            name='date',
            field=models.DateField(
                blank=True,
                help_text="Date de la transaction (par défaut: aujourd'hui)",
                null=True,
                verbose_name='Date',
            ),
        ),
    ]
