# tech_in/models.py
from django.db import models


class RuleCategory(models.Model):
    rule_category_id = models.AutoField(db_column="rule_category_id", primary_key=True)
    rule_category_name = models.CharField(max_length=255)

    class Meta:
        db_table = "rule_categories"
        managed = False

    def __str__(self):
        return self.rule_category_name


class RuleSubCategory(models.Model):
    rule_subcategory_id = models.AutoField(db_column="rule_subcategory_id", primary_key=True)
    category = models.ForeignKey(
        RuleCategory,
        on_delete=models.DO_NOTHING,
        related_name="subcategories",
        db_column="rule_category_id",
    )
    rule_subcategory_name = models.CharField(max_length=255)

    class Meta:
        db_table = "rule_subcategories"
        managed = False

    def __str__(self):
        return f"{self.category.rule_category_name} – {self.rule_subcategory_name}"


class Rule(models.Model):
    rule_id = models.AutoField(db_column="rule_id", primary_key=True)
    sub_category = models.ForeignKey(
        RuleSubCategory,
        on_delete=models.DO_NOTHING,
        related_name="rules",
        db_column="rule_subcategory_id",
    )
    rule_content = models.CharField(max_length=512)
    rule_number = models.CharField(max_length=45)
    class Meta:
        db_table = "rules"
        managed = False

    def __str__(self):
        return self.rule_content


class EventTractorRuleStatus(models.Model):
    event_tractor_rule_status_id = models.AutoField(
        db_column="event_tractor_rule_status_id",
        primary_key=True,
    )

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
    status = models.IntegerField()  # Pass: 3 Corrected: 2 Failed: 1 Not Started: 0

    class Meta:
        db_table = "event_tractor_rule_status"
        managed = False

    def __str__(self):
        return f"{self.event_tractor} – {self.rule.rule_content} – {self.status}"

class RuleTractorMedia(models.Model):
    id=models.AutoField(db_column="rule_tractor_media_id",primary_key=True)
    

    class types(models.IntegerChoices):
        YOUTUBE_VIDEO=1
        IMAGE=2
        COMMENT=3
    
    media_type=models.IntegerField(choices=types)
    event_tractor_rule_status=models.ForeignKey(
        EventTractorRuleStatus,
        on_delete=models.DO_NOTHING,
        related_name="media",
        db_column="event_tractor_rule_status_id"
    )
    class Meta:
        managed = False
        db_table="rule_tractor_media"

    media=models.CharField(max_length=512)