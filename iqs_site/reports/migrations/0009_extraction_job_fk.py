from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0008_bulk_pdf_export"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportpage",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="extracted_pages",
                to="reports.analysisjob",
            ),
        ),
        migrations.AddField(
            model_name="reportimage",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="extracted_images",
                to="reports.analysisjob",
            ),
        ),
    ]
