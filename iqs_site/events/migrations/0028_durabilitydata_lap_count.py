from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0027_enginedata'),
    ]

    # durability_data is an unmanaged table (written by the ROS pull_recorder
    # uploader), so the column is added with raw SQL while AddField keeps the
    # Django model state in sync for the ORM/serializers.
    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE durability_data ADD COLUMN lap_count INT NULL DEFAULT 0;",
            reverse_sql="ALTER TABLE durability_data DROP COLUMN lap_count;",
            state_operations=[
                migrations.AddField(
                    model_name='durabilitydata',
                    name='lap_count',
                    field=models.IntegerField(blank=True, default=0, null=True),
                ),
            ],
        ),
    ]
