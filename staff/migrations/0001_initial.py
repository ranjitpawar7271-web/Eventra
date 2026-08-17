import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0003_event_venue'),
    ]

    operations = [
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='StaffProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('employee_id', models.CharField(max_length=30, unique=True)),
                ('designation', models.CharField(blank=True, max_length=150)),
                ('phone_number', models.CharField(blank=True, max_length=15)),
                ('skills', models.CharField(blank=True, help_text="Comma-separated list, e.g. 'Sound Engineering, First Aid, Crowd Control'", max_length=500)),
                ('hire_date', models.DateField(default=django.utils.timezone.now)),
                ('is_active', models.BooleanField(default=True, help_text='Inactive staff are excluded from auto-assignment.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_profiles_onboarded', to=settings.AUTH_USER_MODEL)),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_members', to='staff.department')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='staff_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['employee_id'],
            },
        ),
        migrations.CreateModel(
            name='ShiftAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text="e.g. 'Registration Desk', 'Sound Check'", max_length=200)),
                ('start_datetime', models.DateTimeField()),
                ('end_datetime', models.DateTimeField()),
                ('status', models.CharField(choices=[('assigned', 'Assigned'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='assigned', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('auto_assigned', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shifts_assigned', to=settings.AUTH_USER_MODEL)),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_shifts', to='events.event')),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shifts', to='staff.staffprofile')),
            ],
            options={
                'ordering': ['start_datetime'],
            },
        ),
        migrations.CreateModel(
            name='AttendanceRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.now)),
                ('check_in', models.DateTimeField(blank=True, null=True)),
                ('check_out', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('present', 'Present'), ('absent', 'Absent'), ('late', 'Late'), ('half_day', 'Half Day')], default='present', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_records', to='staff.shiftassignment')),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='staff.staffprofile')),
            ],
            options={
                'ordering': ['-date'],
                'unique_together': {('staff', 'date')},
            },
        ),
        migrations.CreateModel(
            name='SalaryRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('basic_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('bonus', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('deductions', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid')], default='pending', max_length=20)),
                ('payment_date', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='salary_records', to='staff.staffprofile')),
            ],
            options={
                'ordering': ['-period_start'],
            },
        ),
    ]
