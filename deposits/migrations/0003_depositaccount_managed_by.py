from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('deposits', '0002_deposittransaction_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='depositaccount',
            name='managed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='managed_deposit_accounts',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Responsable du compte',
            ),
        ),
    ]
