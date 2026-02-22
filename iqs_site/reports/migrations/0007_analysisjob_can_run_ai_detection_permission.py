from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0006_analysisjob_event_alter_analysisjob_job_type_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="analysisjob",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("can_run_ai_detection", "Can trigger AI detection runs"),
                ],
            },
        ),
    ]
