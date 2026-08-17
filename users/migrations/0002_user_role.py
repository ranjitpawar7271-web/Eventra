from django.db import migrations, models


def backfill_organizer_role(apps, schema_editor):
    """Any pre-existing user with is_organizer=True should keep acting like
    an Organizer now that the dedicated `role` field exists.
    """
    User = apps.get_model('users', 'User')
    User.objects.filter(is_organizer=True).update(role='organizer')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('super_admin', 'Super Admin'),
                    ('organizer', 'Organizer'),
                    ('staff', 'Staff'),
                    ('vendor', 'Vendor'),
                    ('volunteer', 'Volunteer'),
                    ('participant', 'Participant'),
                ],
                default='participant',
                help_text='Determines which dashboard and permissions the user gets.',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='is_organizer',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Organizers can create and manage events. Kept for backward '
                    'compatibility; automatically kept in sync with `role`.'
                ),
            ),
        ),
        migrations.RunPython(backfill_organizer_role, noop_reverse),
    ]
