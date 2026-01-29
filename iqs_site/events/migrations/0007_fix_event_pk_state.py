from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("events", "0006_scorecategory_scoresubcategory_scorecategoryinstance_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                # Only include this RemoveField if your migration-state Event has an "id" field.
                migrations.RemoveField(model_name="event", name="id"),
                migrations.AlterField(
                    model_name="event",
                    name="event_id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
        ),
    ]
