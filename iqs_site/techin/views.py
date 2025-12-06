# tech_in/views.py
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404
from .models import RuleCategory
from .models import EventTractorRuleStatus, RuleSubCategory, Rule
from events.models import TractorEvent, Event 
from collections import OrderedDict
from .permissions import user_can_access_team
from django.shortcuts import redirect

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
    if user_can_access_team(request.user,tractor_event):
        return render(request, "tech_in/team_detail.html", context)
    else:
        return render(request, "tech_in/permission_denied.html", status=403)

def tech_in_overview(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    categories = list(
        RuleCategory.objects.all().order_by("rule_category_name")
    )

    tractor_events = (
        TractorEvent.objects
        .filter(event=event)     # <--- keep the event filter
        .select_related("team", "event")
        .order_by("team__team_name")
    )

    rows = []
    for te in tractor_events:
        row = {
            "tractor_event": te,
            "team_name": te.team.team_name,
            "event_name": te.event.event_name,
            "category_values": [],
        }

        for cat in categories:
            row["category_values"].append({
                "category": cat,
                "percent_complete": 0,  # placeholder for now
            })

        rows.append(row)

    context = {
        "event": event,
        "categories": categories,
        "rows": rows,
    }
    return render(request, "tech_in/overview.html", context)

def subcategory_detail(request, event_id, subcategory_id):
    """
    Shows one subcategory (within an event context) and lists its rules.
    """
    event = get_object_or_404(Event, pk=event_id)
    subcategory = get_object_or_404(
        RuleSubCategory.objects.select_related("category"),
        pk=subcategory_id,
    )

    rules = (
        Rule.objects
        .filter(sub_category=subcategory)
        .order_by("rule_id")
    )

    context = {
        "event": event,
        "subcategory": subcategory,
        "category": subcategory.category,
        "rules": rules,
    }
    return render(request, "tech_in/subcategory_detail.html", context)

def rule_detail(request, event_id, rule_id):
    """
    Shows a single rule, and for this event, all tractor/team status rows
    (EventTractorRuleStatus) attached to this rule.
    """
    event = get_object_or_404(Event, pk=event_id)
    rule = get_object_or_404(
        Rule.objects.select_related("sub_category__category"),
        pk=rule_id,
    )

    # All tractor-event rule records for this event + rule
    statuses = (
        EventTractorRuleStatus.objects
        .select_related("event_tractor__team")
        .filter(
            rule=rule,
            event_tractor__event=event,
        )
        .order_by("event_tractor__team__team_name")
    )

    STATUS_MAP = {
        0: ("Not Started", "status-not-started"),
        1: ("Failed", "status-failed"),
        2: ("Corrected", "status-corrected"),
        3: ("Pass", "status-pass"),
    }

    status_rows = []
    for rs in statuses:
        label, css_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))
        status_rows.append({
            "tractor_event": rs.event_tractor,
            "team_name": rs.event_tractor.team.team_name,
            "status_label": label,
            "status_class": css_class,
            "raw": rs,
            # placeholders for future:
            "images": [],      # later: attach images per rs
            "comments": [],    # later: attach comments per rs
        })

    context = {
        "event": event,
        "rule": rule,
        "subcategory": rule.sub_category,
        "category": rule.sub_category.category,
        "status_rows": status_rows,
    }
    return render(request, "tech_in/rule_detail.html", context)

def team_tech_overview(request, event_id, tractor_event_id):
    event = get_object_or_404(Event, pk=event_id)
    te = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        pk=tractor_event_id,
        event=event,
    )

    # All categories + their subcategories
    categories = (
        RuleCategory.objects
        .prefetch_related("subcategories")
        .order_by("rule_category_name")
    )

    # For now, all percentages are 0
    category_rows = []
    for cat in categories:
        sub_rows = []
        for subcat in cat.subcategories.all():
            sub_rows.append({
                "subcategory": subcat,
                "percent_complete": 0,   # placeholder
            })

        category_rows.append({
            "category": cat,
            "percent_complete": 0,      # placeholder
            "subcategories": sub_rows,
        })

    context = {
        "event": event,
        "tractor_event": te,
        "team": te.team,
        "category_rows": category_rows,
    }
    return render(request, "tech_in/team_tech_overview.html", context)

def team_subcategory_detail(request, event_id, tractor_event_id, subcategory_id):
    event = get_object_or_404(Event, pk=event_id)
    te = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        pk=tractor_event_id,
        event=event,
    )
    subcategory = get_object_or_404(
        RuleSubCategory.objects.select_related("category"),
        pk=subcategory_id,
    )

    rules = Rule.objects.filter(sub_category=subcategory).order_by("rule_id")

    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor=te, rule__in=rules)
        .select_related("rule")
    )
    status_by_rule_id = {rs.rule.rule_id: rs for rs in statuses_qs}

    STATUS_MAP = {
        0: ("Not Started", "status-not-started"),
        1: ("Failed", "status-failed"),
        2: ("Corrected", "status-corrected"),
        3: ("Pass", "status-pass"),
    }

    rule_rows = []
    for rule in rules:
        rs = status_by_rule_id.get(rule.rule_id)
        if rs:
            label, css_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))
        else:
            label, css_class = ("Not Started", "status-not-started")
            rs = None

        rule_rows.append({
            "rule": rule,
            "status_label": label,
            "status_class": css_class,
            "status_obj": rs,
        })

    context = {
        "event": event,
        "tractor_event": te,
        "team": te.team,
        "subcategory": subcategory,
        "category": subcategory.category,
        "rule_rows": rule_rows,
    }
    return render(request, "tech_in/team_subcategory_detail.html", context)

def team_rule_detail(request, event_id, tractor_event_id, rule_id):
    event = get_object_or_404(Event, pk=event_id)
    te = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        pk=tractor_event_id,
        event=event,
    )
    rule = get_object_or_404(
        Rule.objects.select_related("sub_category__category"),
        pk=rule_id,
    )

    rs = EventTractorRuleStatus.objects.filter(
        event_tractor=te,
        rule=rule,
    ).first()

    STATUS_MAP = {
        0: ("Not Started", "status-not-started"),
        1: ("Failed", "status-failed"),
        2: ("Corrected", "status-corrected"),
        3: ("Pass", "status-pass"),
    }

    if rs:
        status_label, status_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))
    else:
        status_label, status_class = ("Not Started", "status-not-started")

    context = {
        "event": event,
        "tractor_event": te,
        "team": te.team,
        "rule": rule,
        "subcategory": rule.sub_category,
        "category": rule.sub_category.category,
        "status_obj": rs,
        "status_label": status_label,
        "status_class": status_class,
    }
    return render(request, "tech_in/team_rule_detail.html", context)