from django.db import migrations


def backfill(apps, schema_editor):
    RuleCategory = apps.get_model("techin", "RuleCategory")
    RuleSubCategory = apps.get_model("techin", "RuleSubCategory")
    Rule = apps.get_model("techin", "Rule")
    CategoryInstance = apps.get_model("techin", "TechinCategoryInstance")
    SubCategoryInstance = apps.get_model("techin", "TechinSubCategoryInstance")
    RuleInstance = apps.get_model("techin", "TechinRuleInstance")

    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "SELECT DISTINCT te.event_id "
        "FROM event_tractor_rule_status etrs "
        "JOIN tractor_events te ON te.tractor_event_id = etrs.event_tractor_id"
    )
    event_ids = [row[0] for row in cursor.fetchall()]
    if not event_ids:
        return

    # Fetch globals via raw SQL since the migration state of these managed=False
    # models doesn't include the columns we need (db_column='id' in 0001_initial vs
    # current rule_category_id, etc.).
    cursor.execute("SELECT rule_category_id, rule_category_name FROM rule_categories")
    categories = cursor.fetchall()
    cursor.execute("SELECT rule_subcategory_id, rule_category_id FROM rule_subcategories")
    subcategories = cursor.fetchall()
    cursor.execute("SELECT rule_id, rule_subcategory_id FROM rules")
    rules = cursor.fetchall()

    for event_id in event_ids:
        cat_map = {}
        for (cat_id, _name) in categories:
            inst, _ = CategoryInstance.objects.get_or_create(
                event_id=event_id,
                rule_category_id=cat_id,
                defaults={"released": True, "display_order": 0},
            )
            cat_map[cat_id] = inst

        sub_map = {}
        for (sub_id, parent_cat_id) in subcategories:
            parent_cat_inst = cat_map.get(parent_cat_id)
            inst, _ = SubCategoryInstance.objects.get_or_create(
                event_id=event_id,
                rule_subcategory_id=sub_id,
                defaults={
                    "released": True,
                    "display_order": 0,
                    "category_instance": parent_cat_inst,
                },
            )
            if inst.category_instance_id is None and parent_cat_inst is not None:
                inst.category_instance = parent_cat_inst
                inst.save(update_fields=["category_instance"])
            sub_map[sub_id] = inst

        rule_map = {}
        for (rule_id, parent_sub_id) in rules:
            parent_sub_inst = sub_map.get(parent_sub_id)
            inst, _ = RuleInstance.objects.get_or_create(
                event_id=event_id,
                rule_id=rule_id,
                defaults={
                    "subcategory_instance": parent_sub_inst,
                    "rule_number_override": "",
                    "rule_content_override": "",
                    "display_order": 0,
                },
            )
            if inst.subcategory_instance_id is None and parent_sub_inst is not None:
                inst.subcategory_instance = parent_sub_inst
                inst.save(update_fields=["subcategory_instance"])
            rule_map[rule_id] = inst

        # Bulk-update EventTractorRuleStatus.rule_instance_id for this event via raw SQL.
        cursor.execute(
            "UPDATE event_tractor_rule_status etrs "
            "JOIN tractor_events te ON te.tractor_event_id = etrs.event_tractor_id "
            "JOIN rule_instances ri ON ri.event_id = te.event_id AND ri.rule_id = etrs.rule_id "
            "SET etrs.rule_instance_id = ri.rule_instance_id "
            "WHERE te.event_id = %s AND etrs.rule_instance_id IS NULL",
            [event_id],
        )


def noop_reverse(apps, schema_editor):
    RuleInstance = apps.get_model("techin", "TechinRuleInstance")
    SubCategoryInstance = apps.get_model("techin", "TechinSubCategoryInstance")
    CategoryInstance = apps.get_model("techin", "TechinCategoryInstance")
    cursor = schema_editor.connection.cursor()
    cursor.execute("UPDATE event_tractor_rule_status SET rule_instance_id = NULL")
    RuleInstance.objects.all().delete()
    SubCategoryInstance.objects.all().delete()
    CategoryInstance.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("techin", "0005_instance_models"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
