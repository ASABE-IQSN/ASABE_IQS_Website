from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0004_analysisJob_job_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="analysisjob",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("EXTRACTION", "Extraction"),
                    ("SIMILARITY", "Similarity Analysis"),
                    ("FULL", "Full Analysis"),
                ],
                default="FULL",
                max_length=16,
            ),
        ),
    ]
