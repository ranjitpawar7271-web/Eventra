import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Venue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=220, unique=True)),
                ('address', models.CharField(max_length=255)),
                ('city', models.CharField(max_length=100)),
                ('capacity', models.PositiveIntegerField(help_text='Maximum number of people the venue can hold.')),
                ('facilities', models.CharField(blank=True, help_text="Comma-separated list, e.g. 'Wi-Fi, Parking, Projector, AC'", max_length=500)),
                ('description', models.TextField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='venue_images/')),
                ('is_active', models.BooleanField(default=True, help_text='Inactive venues are hidden from booking but keep their history.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='venues_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='VenueBooking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('purpose', models.CharField(blank=True, max_length=255)),
                ('start_datetime', models.DateTimeField()),
                ('end_datetime', models.DateTimeField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')], default='confirmed', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('booked_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='venue_bookings', to=settings.AUTH_USER_MODEL)),
                ('event', models.ForeignKey(blank=True, help_text='Linked automatically when an event selects this venue.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='venue_bookings', to='events.event')),
                ('venue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='venues.venue')),
            ],
            options={
                'ordering': ['start_datetime'],
            },
        ),
        migrations.CreateModel(
            name='MaintenanceSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(max_length=255)),
                ('start_datetime', models.DateTimeField()),
                ('end_datetime', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='maintenance_schedules_created', to=settings.AUTH_USER_MODEL)),
                ('venue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='maintenance_windows', to='venues.venue')),
            ],
            options={
                'verbose_name_plural': 'Maintenance schedules',
                'ordering': ['start_datetime'],
            },
        ),
    ]
