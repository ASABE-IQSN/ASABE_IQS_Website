from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0010_similarity_job_fk"),
    ]

    operations = [
        # Add job FK
        migrations.AddField(
            model_name="aidetectionresult",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ai_detection_results",
                to="reports.analysisjob",
            ),
        ),
        # Add detector field (defaults to ZEROGPT so existing rows stay valid)
        migrations.AddField(
            model_name="aidetectionresult",
            name="detector",
            field=models.CharField(
                choices=[
                    ("ZEROGPT", "ZeroGPT"),
                    ("GPTZERO", "GPTZero"),
                    ("COPYLEAKS", "Copyleaks"),
                ],
                default="ZEROGPT",
                max_length=16,
            ),
        ),
        # Rename zerogpt_id → source_id
        migrations.RenameField(
            model_name="aidetectionresult",
            old_name="zerogpt_id",
            new_name="source_id",
        ),
        # Change page from OneToOneField to ForeignKey
        # Django stores both as FK at DB level; we just change the field type
        migrations.AlterField(
            model_name="aidetectionresult",
            name="page",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ai_detections",
                to="reports.reportpage",
            ),
        ),
        # Add per-job-page-detector unique constraint
        migrations.AddConstraint(
            model_name="aidetectionresult",
            constraint=models.UniqueConstraint(
                fields=["job", "page", "detector"],
                name="uniq_ai_result_per_job_detector",
            ),
        ),
    ]
