from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0003_rename_reports_ima_hamming_idx_reports_ima_hamming_52e280_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysisjob",
            name="job_type",
            field=models.CharField(
                choices=[("EXTRACTION", "Extraction"), ("FULL", "Full Analysis")],
                default="FULL",
                max_length=16,
            ),
        ),
    ]
