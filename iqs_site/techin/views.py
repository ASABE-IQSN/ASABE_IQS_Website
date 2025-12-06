# tech_in/views.py
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404
from .models import RuleCategory
from .models import EventTractorRuleStatus, RuleSubCategory
from events.models import TractorEvent  # adjust app name if needed
from collections import OrderedDict

def tech_in_overview(request):
    # All rule categories become columns
    categories = list(
        RuleCategory.objects.all().order_by("rule_category_name")
    )

    # All tractors at events – one row per tractor/team
    tractor_events = (
        TractorEvent.objects
        .filter(event_id=25,team__team_class=1)
        .select_related("team", "event")
        .order_by("event__event_name", "team__team_name")
    )

    rows = []
    for te in tractor_events:
        row = {
            "tractor_event": te,
            "team_name": te.team.team_name,
            "event_name": te.event.event_name,
            "category_values": [],
        }

        # For now, completion is hard-coded to 0%
        for cat in categories:
            row["category_values"].append({
                "category": cat,
                "percent_complete": 0,
            })

        rows.append(row)

    context = {
        "categories": categories,
        "rows": rows,
    }
    return render(request, "tech_in/overview.html", context)


def tech_in_team_detail(request, tractor_event_id):
    """
    Detail view for a single TractorEvent (team at an event).

    Now groups rule statuses as:
        Category → Subcategory → [rules]
    so the template can render one big block per category.
    """
    tractor_event = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        pk=tractor_event_id,
    )

    # Load all rule statuses for this tractor
    rule_statuses = (
        EventTractorRuleStatus.objects
        .select_related(
            "rule",
            "rule__sub_category",
            "rule__sub_category__category",
        )
        .filter(event_tractor=tractor_event)
        .order_by(
            "rule__sub_category__category__rule_category_name",
            "rule__sub_category__rule_subcategory_name",
            "rule__rule_id",
        )
    )

    STATUS_MAP = {
        0: ("Not Started", "status-not-started"),
        1: ("Failed", "status-failed"),
        2: ("Corrected", "status-corrected"),
        3: ("Pass", "status-pass"),
    }

    # Build:
    # categories[cat_id] = {
    #   "category": <RuleCategory>,
    #   "subcategories": OrderedDict({
    #       subcat_id: {
    #           "subcategory": <RuleSubCategory>,
    #           "rules": [ { rule, status_label, status_class } ... ]
    #       }
    #   })
    # }
    categories = OrderedDict()

    for rs in rule_statuses:
        subcat = rs.rule.sub_category
        cat = subcat.category

        cat_id = cat.rule_category_id
        subcat_id = subcat.rule_subcategory_id

        if cat_id not in categories:
            categories[cat_id] = {
                "category": cat,
                "subcategories": OrderedDict(),
            }

        if subcat_id not in categories[cat_id]["subcategories"]:
            categories[cat_id]["subcategories"][subcat_id] = {
                "subcategory": subcat,
                "rules": [],
            }

        label, css_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))

        categories[cat_id]["subcategories"][subcat_id]["rules"].append({
            "rule": rs.rule,
            "status": rs.status,
            "status_label": label,
            "status_class": css_class,
        })

    context = {
        "tractor_event": tractor_event,
        "team": tractor_event.team,
        "event": tractor_event.event,
        "categories": categories.values(),  # list of {category, subcategories}
    }
    return render(request, "tech_in/team_detail.html", context)
