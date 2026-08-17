import django.db.models.deletion
import django.core.validators
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
            name='VendorProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=220, unique=True)),
                ('service_type', models.CharField(choices=[
                    ('catering', 'Catering'), ('decoration', 'Decoration'),
                    ('photography', 'Photography & Videography'), ('security', 'Security'),
                    ('transport', 'Transport'), ('sound_lighting', 'Sound & Lighting'),
                    ('printing', 'Printing & Branding'), ('other', 'Other'),
                ], default='other', max_length=30)),
                ('contact_person', models.CharField(blank=True, max_length=150)),
                ('phone_number', models.CharField(blank=True, max_length=15)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('description', models.TextField(blank=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='vendor_logos/')),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending Approval'), ('approved', 'Approved'),
                    ('rejected', 'Rejected'), ('suspended', 'Suspended'),
                ], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_profiles_reviewed', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vendor_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['company_name'],
            },
        ),
        migrations.CreateModel(
            name='VendorService',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('price_unit', models.CharField(choices=[
                    ('flat', 'Flat rate'), ('per_hour', 'Per hour'), ('per_day', 'Per day'),
                    ('per_person', 'Per person'), ('per_event', 'Per event'),
                ], default='flat', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='services', to='vendors.vendorprofile')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='VendorDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('document_type', models.CharField(choices=[
                    ('license', 'Business License'), ('certification', 'Certification'),
                    ('insurance', 'Insurance Proof'), ('contract', 'Contract'), ('other', 'Other'),
                ], default='other', max_length=20)),
                ('file', models.FileField(upload_to='vendor_documents/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='vendors.vendorprofile')),
            ],
            options={
                'ordering': ['-uploaded_at'],
            },
        ),
        migrations.CreateModel(
            name='VendorContract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('document', models.FileField(blank=True, null=True, upload_to='vendor_contracts/')),
                ('status', models.CharField(choices=[
                    ('draft', 'Draft'), ('sent', 'Sent'), ('signed', 'Signed'),
                    ('completed', 'Completed'), ('cancelled', 'Cancelled'),
                ], default='draft', max_length=20)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_contracts_created', to=settings.AUTH_USER_MODEL)),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_contracts', to='events.event')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contracts', to='vendors.vendorprofile')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VendorRating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_quality', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('delivery_time', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor_ratings', to='events.event')),
                ('rated_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings', to='vendors.vendorprofile')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VendorPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('method', models.CharField(choices=[
                    ('bank_transfer', 'Bank Transfer'), ('upi', 'UPI'), ('cheque', 'Cheque'),
                    ('cash', 'Cash'), ('other', 'Other'),
                ], default='bank_transfer', max_length=20)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'),
                ], default='pending', max_length=20)),
                ('reference_note', models.CharField(blank=True, max_length=255)),
                ('payment_date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contract', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='vendors.vendorcontract')),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='vendors.vendorprofile')),
            ],
            options={
                'ordering': ['-payment_date'],
            },
        ),
    ]
