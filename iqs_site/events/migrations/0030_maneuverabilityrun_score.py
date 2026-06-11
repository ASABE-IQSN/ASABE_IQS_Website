from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0029_durabilitydata_time_remaining'),
    ]

    # maneuverability_runs is an unmanaged table (written by the live event
    # services). The score column is added with raw SQL while AddField keeps the
    # Django model state in sync for the ORM/serializers. Mirrors the pattern in
    # 0028_durabilitydata_lap_count.
    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE maneuverability_runs ADD COLUMN score FLOAT NULL;",
            reverse_sql="ALTER TABLE maneuverability_runs DROP COLUMN score;",
            state_operations=[
                migrations.AddField(
                    model_name='maneuverabilityrun',
                    name='score',
                    field=models.FloatField(blank=True, null=True),
                ),
            ],
        ),
    ]
