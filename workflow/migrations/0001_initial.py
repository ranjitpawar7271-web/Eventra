import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkflowSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('require_event_approval', models.BooleanField(default=False, help_text="If on, an Event moving to Published is held back as Draft until a Super Admin/Staff member approves it. Off by default so existing organizer workflows aren't interrupted until someone deliberately opts in.")),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workflow_settings_updates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Workflow settings',
                'verbose_name_plural': 'Workflow settings',
            },
        ),
        migrations.CreateModel(
            name='ApprovalStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('stage', models.CharField(choices=[('planning', 'Planning'), ('approval', 'Approval'), ('published', 'Published'), ('registration', 'Registration'), ('execution', 'Execution'), ('completed', 'Completed'), ('archived', 'Archived')], default='approval', max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('comment', models.TextField(blank=True, help_text="Approver's note, especially for a rejection.")),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approval_steps_decided', to=settings.AUTH_USER_MODEL)),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approval_steps_requested', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-requested_at'],
            },
        ),
        migrations.AddIndex(
            model_name='approvalstep',
            index=models.Index(fields=['content_type', 'object_id'], name='workflow_ap_content_c6f2f7_idx'),
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.CharField(max_length=255)),
                ('link', models.CharField(blank=True, help_text='In-app URL this notification points to.', max_length=255)),
                ('notification_type', models.CharField(choices=[('approval', 'Approval'), ('reminder', 'Reminder'), ('staff', 'Staff'), ('vendor', 'Vendor'), ('payment', 'Payment'), ('announcement', 'Announcement'), ('system', 'System')], default='system', max_length=20)),
                ('is_read', models.BooleanField(default=False)),
                ('dedupe_key', models.CharField(blank=True, help_text="Set by scheduled rules so re-running send_reminders doesn't duplicate this notification.", max_length=140, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read'], name='workflow_no_user_id_5f2b8e_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='notification',
            unique_together={('user', 'dedupe_key')},
        ),
    ]
