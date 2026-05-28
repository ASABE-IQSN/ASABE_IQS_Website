from django.db import migrations, models


def backfill_sheet(apps, schema_editor):
    """Seed each category instance's sheet_name/sheet_key from the legacy
    per-template values on rule_categories, so existing events keep working."""
    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "UPDATE rule_category_instances ci "
        "JOIN rule_categories c ON c.rule_category_id = ci.rule_category_id "
        "SET ci.sheet_name = COALESCE(c.sheet_name, ''), "
        "    ci.sheet_key = COALESCE(c.sheet_key, '')"
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("techin", "0006_backfill_instances"),
    ]

    operations = [
        migrations.AddField(
            model_name="techincategoryinstance",
            name="sheet_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="techincategoryinstance",
            name="sheet_key",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunPython(backfill_sheet, noop_reverse),
    ]
