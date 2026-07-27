import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0017_onlineseller_productcirculation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Repoint "vendeuse" to app user accounts. The feature is new, so any
        # existing OnlineSeller-based assignments are dropped (field removed
        # then re-added against the user model).
        migrations.RemoveField(
            model_name='productcirculation',
            name='seller',
        ),
        migrations.AddField(
            model_name='productcirculation',
            name='seller',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='circulations_as_seller',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Vendeuse',
            ),
        ),
        migrations.DeleteModel(
            name='OnlineSeller',
        ),
    ]
