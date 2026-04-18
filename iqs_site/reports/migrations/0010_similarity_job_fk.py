from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0009_extraction_job_fk"),
    ]

    operations = [
        # PageMatch: drop old unique constraint, add job FK, add new per-job constraint
        migrations.RemoveConstraint(
            model_name="pagematch",
            name="uniq_page_match",
        ),
        migrations.AddField(
            model_name="pagematch",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="page_matches",
                to="reports.analysisjob",
            ),
        ),
        migrations.AddConstraint(
            model_name="pagematch",
            constraint=models.UniqueConstraint(
                fields=["job", "page_a", "page_b"],
                name="uniq_page_match_per_job",
            ),
        ),
        # ImageMatch: drop old unique constraint, add job FK, add new per-job constraint
        migrations.RemoveConstraint(
            model_name="imagematch",
            name="uniq_image_match",
        ),
        migrations.AddField(
            model_name="imagematch",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="image_matches",
                to="reports.analysisjob",
            ),
        ),
        migrations.AddConstraint(
            model_name="imagematch",
            constraint=models.UniqueConstraint(
                fields=["job", "image_a", "image_b"],
                name="uniq_image_match_per_job",
            ),
        ),
    ]
