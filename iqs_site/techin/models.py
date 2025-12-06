# tech_in/models.py
from django.db import models


class RuleCategory(models.Model):
    # Adjust column names to match your DB
    rule_catagory_id = models.AutoField(db_column="rule_catagory_id", primary_key=True)
    rule_catagory_name = models.CharField(max_length=255)

    class Meta:
        db_table = "rule_catagories"   # note your spelling
        managed = False                # DB already exists

    def __str__(self):
        return self.name


class RuleSubCategory(models.Model):
    rule_subcatagory_id = models.AutoField(db_column="rule_subcatagory_id", primary_key=True)
    category = models.ForeignKey(
        RuleCategory,
        on_delete=models.DO_NOTHING,
        related_name="subcategories",
        db_column="rule_catagory_id",
    )
    rule_subcatagory_name = models.CharField(max_length=255)

    class Meta:
        db_table = "rule_subcatagories"
        managed = False

    def __str__(self):
        return f"{self.category.name} – {self.rule_subcatagory_name}"


class Rule(models.Model):
    rule_id = models.AutoField(db_column="rule_id", primary_key=True)
    sub_category = models.ForeignKey(
        RuleSubCategory,
        on_delete=models.DO_NOTHING,
        related_name="rules",
        db_column="rule_subcatagory_id",
    )
    rule_content=models.CharField(max_length=512)

    class Meta:
        db_table = "rules"
        managed = False

    def __str__(self):
        return self.code


class EventTractorRuleStatus(models.Model):
    

    event_tractor_rule_status_id = models.AutoField(db_column="event_tractor_rule_status_id", primary_key=True)

    # Change 'events' to whatever app your EventTractor is in
    event_tractor = models.ForeignKey(
        "events.TractorEvent",
        on_delete=models.DO_NOTHING,
        related_name="rule_statuses",
        db_column="event_tractor_id",
    )
    rule = models.ForeignKey(
        Rule,
        on_delete=models.DO_NOTHING,
        related_name="statuses",
        db_column="rule_id",
    )
    status = models.IntegerField()
    

    class Meta:
        db_table = "event_tractor_rule_status"
        managed = False

    def __str__(self):
        return f"{self.event_tractor} – {self.rule.code} – {self.status}"
