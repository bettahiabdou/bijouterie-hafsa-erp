from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0010_zebra_label_font_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='systemconfig',
            name='telegram_chat_id',
            field=models.CharField(blank=True, max_length=500, verbose_name='Chat ID Telegram'),
        ),
    ]
