from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import RuleCategory, RuleSubCategory, Rule, EventTractorRuleStatus

@admin.register(RuleCategory)
class RuleCategoryAdmin(admin.ModelAdmin):
    list_display = ("rule_category_id", "rule_category_name")
    search_fields = ("rule_category_name",)
    ordering = ("rule_category_name",)

@admin.register(RuleSubCategory)
class RuleSubCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "rule_subcategory_id",
        "rule_subcategory_name",
        "category",
    )
    list_filter = ("category",)
    search_fields = ("rule_subcategory_name", "category__rule_category_name")
    ordering = ("category__rule_category_name", "rule_subcategory_name")

@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("rule_id", "sub_category", "short_content")
    list_filter = ("sub_category__category", "sub_category")
    search_fields = ("rule_content", "sub_category__rule_subcategory_name")
    ordering = ("sub_category__category__rule_category_name",
                "sub_category__rule_subcategory_name",
                "rule_id")

    def short_content(self, obj):
        text = obj.rule_content or ""
        return text if len(text) <= 80 else text[:77] + "..."
    short_content.short_description = "Rule Text"

@admin.register(EventTractorRuleStatus)
class EventTractorRuleStatusAdmin(admin.ModelAdmin):
    list_display = (
        "event_tractor",
        "team_name",
        "event_name",
        "rule",
        "status_label",
    )
    list_filter = (
        "status",
        "event_tractor__event",
        "event_tractor__team",
    )
    search_fields = (
        "event_tractor__team__team_name",
        "event_tractor__event__event_name",
        "rule__rule_content",
    )
    ordering = (
        "event_tractor__event__event_name",
        "event_tractor__team__team_name",
        "rule__rule_id",
    )

    def team_name(self, obj):
        return obj.event_tractor.team.team_name
    team_name.short_description = "Team"

    def event_name(self, obj):
        return obj.event_tractor.event.event_name
    event_name.short_description = "Event"

    def status_label(self, obj):
        mapping = {
            0: "Not Started",
            1: "Failed",
            2: "Corrected",
            3: "Pass",
        }
        return mapping.get(obj.status, f"Unknown ({obj.status})")
    status_label.short_description = "Status"