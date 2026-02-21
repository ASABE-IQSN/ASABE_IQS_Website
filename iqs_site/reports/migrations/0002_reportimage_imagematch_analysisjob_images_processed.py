import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        # Add images_processed counter to AnalysisJob
        migrations.AddField(
            model_name="analysisjob",
            name="images_processed",
            field=models.IntegerField(default=0),
        ),
        # ReportImage model
        migrations.CreateModel(
            name="ReportImage",
            fields=[
                ("image_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "report",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="events.report",
                    ),
                ),
                ("page_number", models.IntegerField()),
                ("image_index", models.IntegerField()),
                ("phash", models.CharField(max_length=16)),
                ("width", models.IntegerField()),
                ("height", models.IntegerField()),
            ],
            options={
                "ordering": ["report", "page_number", "image_index"],
            },
        ),
        migrations.AddIndex(
            model_name="reportimage",
            index=models.Index(fields=["report", "page_number"], name="reports_rep_report__img_idx"),
        ),
        # ImageMatch model
        migrations.CreateModel(
            name="ImageMatch",
            fields=[
                ("image_match_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "image_a",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="matches_as_a",
                        to="reports.reportimage",
                    ),
                ),
                (
                    "image_b",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="matches_as_b",
                        to="reports.reportimage",
                    ),
                ),
                ("hamming_distance", models.IntegerField()),
            ],
            options={
                "ordering": ["hamming_distance"],
            },
        ),
        migrations.AddIndex(
            model_name="imagematch",
            index=models.Index(fields=["hamming_distance"], name="reports_ima_hamming_idx"),
        ),
        migrations.AddConstraint(
            model_name="imagematch",
            constraint=models.UniqueConstraint(fields=["image_a", "image_b"], name="uniq_image_match"),
        ),
    ]
