import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_initial'),
        ('venues', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='location',
            field=models.CharField(
                help_text='Free-text venue/location name, used when no registered Venue is selected.',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='event',
            name='venue',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='events',
                to='venues.venue',
                help_text='Optional: link to a managed Venue for booking, conflict detection, and capacity checks.',
            ),
        ),
    ]
