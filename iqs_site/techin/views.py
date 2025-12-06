# tech_in/views.py
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404

from .models import EventTractorRuleStatus, RuleSubCategory
from events.models import TractorEvent  # adjust app name if needed


def tech_in_overview(request):
    """
    Show, for each EventTractor, the status of each rule subcategory.
    """
    # Aggregate per (event_tractor, subcategory)
    agg = (
        EventTractorRuleStatus.objects
        .select_related(
            "event_tractor__team",
            "event_tractor__event",
            "rule__sub_category",
            "rule__sub_category__category",
        )
        .values(
            "event_tractor_id",
            "event_tractor__team__team_name",
            "event_tractor__team_id",
            "event_tractor__event_id",
            "rule__sub_category_id",
            "rule__sub_category__rule_subcatagory_name",
            "rule__sub_category__category__rule_catagory_name",
        )
        .annotate(
            total_rules=Count("event_tractor_rule_status_id"),
            passed_rules=Count("event_tractor_rule_status_id", filter=Q(status=3)),
            failed_rules=Count("event_tractor_rule_status_id", filter=Q(status=1)),
        )
    )

    # Build a structured object:
    # tractors[event_tractor_id] = {
    #   "team_name": ...,
    #   "event_id": ...,
    #   "subcategories": [
    #       { "id": ..., "name": ..., "category_name": ..., "status": ... }
    #   ]
    # }
    tractors = {}
    for row in agg:
        et_id = row["event_tractor_id"]
        if et_id not in tractors:
            tractors[et_id] = {
                "event_tractor_id": et_id,
                "team_name": row["event_tractor__team__team_name"],
                "event_id": row["event_tractor__event_id"],
                "subcategories": [],
            }

        if row["failed_rules"] > 0:
            status = "FAIL"
        elif row["passed_rules"] == row["total_rules"]:
            status = "PASS"
        else:
            status = "IN PROGRESS"

        tractors[et_id]["subcategories"].append({
            "id": row["rule__sub_category_id"],
            "name": row["rule__sub_category__rule_subcatagory_name"],
            "category_name": row["rule__sub_category__category__rule_catagory_name"],
            "status": status,
        })

    context = {
        "tractors": tractors.values(),
    }
    return render(request, "tech_in/overview.html", context)


def tech_in_detail(request, event_tractor_id, subcategory_id):
    """
    Detail view for one EventTractor + one RuleSubCategory.
    Shows each individual rule and status.
    """
    event_tractor = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        pk=event_tractor_id,
    )
    subcategory = get_object_or_404(
        RuleSubCategory.objects.select_related("category"),
        pk=subcategory_id,
    )

    rule_statuses = (
        EventTractorRuleStatus.objects
        .select_related("rule")
        .filter(
            event_tractor_id=event_tractor_id,
            rule__sub_category_id=subcategory_id,
        )
        .order_by("rule__code")
    )

    context = {
        "event_tractor": event_tractor,
        "subcategory": subcategory,
        "rule_statuses": rule_statuses,
    }
    return render(request, "tech_in/detail.html", context)
