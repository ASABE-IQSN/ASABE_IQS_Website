import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0025_event_scores_released"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScoreSheetSubmission",
            fields=[
                ("submission_id", models.AutoField(primary_key=True, serialize=False)),
                ("file_path", models.CharField(max_length=255)),
                ("original_filename", models.CharField(max_length=255)),
                ("submitted_from_ip", models.CharField(blank=True, max_length=255, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(default=datetime.datetime.utcnow)),
            ],
            options={
                "db_table": "score_sheet_submissions",
                "managed": True,
            },
        ),
    ]
