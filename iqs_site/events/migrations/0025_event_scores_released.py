from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0024_scorecategoryinstance_display_order_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE events ADD COLUMN scores_released TINYINT(1) NOT NULL DEFAULT 0",
                    reverse_sql="ALTER TABLE events DROP COLUMN scores_released",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="event",
                    name="scores_released",
                    field=models.BooleanField(default=False),
                ),
            ],
        ),
    ]
