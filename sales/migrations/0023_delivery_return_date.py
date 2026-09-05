from django.db import migrations, models


def backfill_return_date(apps, schema_editor):
    """For existing returns, set return_date from the timeline: the event that
    mentions 'retour', else the most recent event."""
    Delivery = apps.get_model('sales', 'Delivery')
    Event = apps.get_model('sales', 'DeliveryTimelineEvent')
    for d in Delivery.objects.filter(status='returned', return_date=''):
        events = list(Event.objects.filter(delivery=d))
        if not events:
            continue
        chosen = None
        for e in events:
            if 'retour' in (e.description or '').lower():
                chosen = e
                break
        if chosen is None:
            chosen = max(events, key=lambda e: (e.created_at is not None, e.created_at))
        if chosen and chosen.event_date:
            d.return_date = chosen.event_date
            d.save(update_fields=['return_date'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0022_alter_dataexportjob_id_deliveryphoto'),
    ]

    operations = [
        migrations.AddField(
            model_name='delivery',
            name='return_date',
            field=models.CharField(blank=True, max_length=50, verbose_name='Date de retour'),
        ),
        migrations.RunPython(backfill_return_date, noop),
    ]
