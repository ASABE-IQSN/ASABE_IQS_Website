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


class TechinCategoryInstance(models.Model):
    rule_category_instance_id = models.AutoField(primary_key=True)
    rule_category = models.ForeignKey(
        RuleCategory,
        on_delete=models.DO_NOTHING,
        related_name="instances",
        db_column="rule_category_id",
        db_constraint=False,
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.DO_NOTHING,
        related_name="techin_category_instances",
        db_column="event_id",
    )
    released = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)

    class Meta:
        managed = True
        db_table = "rule_category_instances"

    def __str__(self):
        return f"{self.event} – {self.rule_category}"

    @property
    def rule_category_name(self):
        return self.rule_category.rule_category_name


class TechinSubCategoryInstance(models.Model):
    rule_subcategory_instance_id = models.AutoField(primary_key=True)
    rule_subcategory = models.ForeignKey(
        RuleSubCategory,
        on_delete=models.DO_NOTHING,
        related_name="instances",
        db_column="rule_subcategory_id",
        db_constraint=False,
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.DO_NOTHING,
        related_name="techin_subcategory_instances",
        db_column="event_id",
    )
    category_instance = models.ForeignKey(
        TechinCategoryInstance,
        on_delete=models.DO_NOTHING,
        related_name="subcategory_instances",
        db_column="rule_category_instance_id",
        null=True,
        blank=True,
        db_constraint=False,
    )
    released = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)

    class Meta:
        managed = True
        db_table = "rule_subcategory_instances"

    def __str__(self):
        return f"{self.event} – {self.rule_subcategory}"

    @property
    def rule_subcategory_name(self):
        return self.rule_subcategory.rule_subcategory_name


class TechinRuleInstance(models.Model):
    rule_instance_id = models.AutoField(primary_key=True)
    rule = models.ForeignKey(
        Rule,
        on_delete=models.DO_NOTHING,
        related_name="instances",
        db_column="rule_id",
        db_constraint=False,
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.DO_NOTHING,
        related_name="techin_rule_instances",
        db_column="event_id",
    )
    subcategory_instance = models.ForeignKey(
        TechinSubCategoryInstance,
        on_delete=models.DO_NOTHING,
        related_name="rule_instances",
        db_column="rule_subcategory_instance_id",
        null=True,
        blank=True,
        db_constraint=False,
    )
    rule_number_override = models.CharField(max_length=45, blank=True, default="")
    rule_content_override = models.CharField(max_length=512, blank=True, default="")
    display_order = models.IntegerField(default=0)

    class Meta:
        managed = True
        db_table = "rule_instances"

    def __str__(self):
        return f"{self.event} – {self.rule_content}"

    @property
    def rule_number(self):
        return self.rule_number_override or self.rule.rule_number

    @property
    def rule_content(self):
        return self.rule_content_override or self.rule.rule_content


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
        null=True,
        blank=True,
    )
    rule_instance = models.ForeignKey(
        TechinRuleInstance,
        on_delete=models.DO_NOTHING,
        related_name="statuses",
        db_column="rule_instance_id",
        null=True,
        blank=True,
        db_constraint=False,
    )
    status = models.IntegerField()  # Pass: 3 Corrected: 2 Failed: 1 Not Started: 0

    class Meta:
        db_table = "event_tractor_rule_status"
        managed = False

    def __str__(self):
        label = self.rule_instance.rule_content if self.rule_instance_id else (
            self.rule.rule_content if self.rule_id else "?"
        )
        return f"{self.event_tractor} – {label} – {self.status}"

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