import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0003_event_venue'),
    ]

    operations = [
        migrations.CreateModel(
            name='Resource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=220, unique=True)),
                ('category', models.CharField(choices=[
                    ('chairs', 'Chairs'), ('tables', 'Tables'), ('projectors', 'Projectors'),
                    ('sound_systems', 'Sound Systems'), ('lights', 'Lights'), ('vehicles', 'Vehicles'),
                    ('generators', 'Generators'), ('decoration', 'Decoration Items'), ('other', 'Other'),
                ], default='other', max_length=20)),
                ('description', models.TextField(blank=True)),
                ('total_quantity', models.PositiveIntegerField(help_text='Total units owned/available in inventory.')),
                ('unit', models.CharField(default='pcs', help_text='e.g. pcs, sets, units', max_length=30)),
                ('image', models.ImageField(blank=True, null=True, upload_to='resource_images/')),
                ('is_active', models.BooleanField(default=True, help_text='Inactive resources are hidden from allocation.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resources_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['category', 'name'],
            },
        ),
        migrations.CreateModel(
            name='ResourceAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField()),
                ('purpose', models.CharField(blank=True, max_length=255)),
                ('start_datetime', models.DateTimeField()),
                ('end_datetime', models.DateTimeField()),
                ('status', models.CharField(choices=[('allocated', 'Allocated'), ('returned', 'Returned'), ('cancelled', 'Cancelled')], default='allocated', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='resource_allocations', to='events.event')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='resource_allocations', to=settings.AUTH_USER_MODEL)),
                ('resource', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocations', to='resources.resource')),
            ],
            options={
                'ordering': ['start_datetime'],
            },
        ),
        migrations.CreateModel(
            name='DamageReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity_damaged', models.PositiveIntegerField(default=1)),
                ('severity', models.CharField(choices=[('minor', 'Minor'), ('major', 'Major'), ('critical', 'Critical')], default='minor', max_length=20)),
                ('description', models.TextField()),
                ('status', models.CharField(choices=[('reported', 'Reported'), ('under_repair', 'Under Repair'), ('resolved', 'Resolved')], default='reported', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('allocation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='damage_reports', to='resources.resourceallocation')),
                ('reported_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='damage_reports_filed', to=settings.AUTH_USER_MODEL)),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='damage_reports_resolved', to=settings.AUTH_USER_MODEL)),
                ('resource', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='damage_reports', to='resources.resource')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
