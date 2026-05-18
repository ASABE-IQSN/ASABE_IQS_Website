from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("techin", "0004_ruletractormedia"),
        ("events", "0026_scoresheetsubmission"),
    ]

    operations = [
        migrations.CreateModel(
            name="TechinCategoryInstance",
            fields=[
                ("rule_category_instance_id", models.AutoField(primary_key=True, serialize=False)),
                ("released", models.BooleanField(default=False)),
                ("display_order", models.IntegerField(default=0)),
                ("rule_category", models.ForeignKey(
                    db_column="rule_category_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="instances",
                    to="techin.rulecategory",
                    db_constraint=False,
                )),
                ("event", models.ForeignKey(
                    db_column="event_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="techin_category_instances",
                    to="events.event",
                )),
            ],
            options={
                "db_table": "rule_category_instances",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="TechinSubCategoryInstance",
            fields=[
                ("rule_subcategory_instance_id", models.AutoField(primary_key=True, serialize=False)),
                ("released", models.BooleanField(default=False)),
                ("display_order", models.IntegerField(default=0)),
                ("rule_subcategory", models.ForeignKey(
                    db_column="rule_subcategory_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="instances",
                    to="techin.rulesubcategory",
                    db_constraint=False,
                )),
                ("event", models.ForeignKey(
                    db_column="event_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="techin_subcategory_instances",
                    to="events.event",
                )),
                ("category_instance", models.ForeignKey(
                    db_column="rule_category_instance_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="subcategory_instances",
                    to="techin.techincategoryinstance",
                    null=True,
                    blank=True,
                    db_constraint=False,
                )),
            ],
            options={
                "db_table": "rule_subcategory_instances",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="TechinRuleInstance",
            fields=[
                ("rule_instance_id", models.AutoField(primary_key=True, serialize=False)),
                ("rule_number_override", models.CharField(blank=True, default="", max_length=45)),
                ("rule_content_override", models.CharField(blank=True, default="", max_length=512)),
                ("display_order", models.IntegerField(default=0)),
                ("rule", models.ForeignKey(
                    db_column="rule_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="instances",
                    to="techin.rule",
                    db_constraint=False,
                )),
                ("event", models.ForeignKey(
                    db_column="event_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="techin_rule_instances",
                    to="events.event",
                )),
                ("subcategory_instance", models.ForeignKey(
                    db_column="rule_subcategory_instance_id",
                    on_delete=models.deletion.DO_NOTHING,
                    related_name="rule_instances",
                    to="techin.techinsubcategoryinstance",
                    null=True,
                    blank=True,
                    db_constraint=False,
                )),
            ],
            options={
                "db_table": "rule_instances",
                "managed": True,
            },
        ),
        # event_tractor_rule_status is managed=False, so add rule_instance_id column via raw SQL.
        migrations.RunSQL(
            sql=(
                "ALTER TABLE event_tractor_rule_status "
                "ADD COLUMN rule_instance_id INT NULL, "
                "ADD INDEX idx_etrs_rule_instance_id (rule_instance_id), "
                "MODIFY COLUMN rule_id INT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE event_tractor_rule_status "
                "DROP INDEX idx_etrs_rule_instance_id, "
                "DROP COLUMN rule_instance_id, "
                "MODIFY COLUMN rule_id INT NOT NULL;"
            ),
        ),
    ]
