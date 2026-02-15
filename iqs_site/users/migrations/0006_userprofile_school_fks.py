"""
Custom migration to convert school fields from CharField to ForeignKey(Team).

Note: The school_name column was already dropped by a partially-applied
previous migration attempt, so we only need to add the new columns and
handle alumni_school conversion.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
        ('users', '0005_userprofile'),
    ]

    operations = [
        # Remove school_name from Django state only (column already dropped at DB level)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='userprofile',
                    name='school_name',
                ),
            ],
            database_operations=[],
        ),
        # Add school_id column
        migrations.AddField(
            model_name='userprofile',
            name='school',
            field=models.ForeignKey(
                blank=True,
                db_column='school_id',
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='student_profiles',
                to='events.team',
            ),
        ),
        # Drop old alumni_school varchar column and add as FK
        migrations.RemoveField(
            model_name='userprofile',
            name='alumni_school',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='alumni_school',
            field=models.ForeignKey(
                blank=True,
                db_column='alumni_school_id',
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='alumni_profiles',
                to='events.team',
            ),
        ),
    ]
