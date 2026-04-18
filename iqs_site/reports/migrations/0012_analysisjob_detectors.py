from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0011_ai_detection_multi_detector"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysisjob",
            name="detectors",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Comma-separated detector keys to use for AI_DETECTION jobs (empty = all configured).",
                max_length=64,
            ),
        ),
    ]
