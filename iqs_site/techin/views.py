# tech_in/views.py
import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST

from collections import OrderedDict

from events.models import Event, Team, TractorEvent

from .models import (
    EventTractorRuleStatus,
    RuleTractorMedia,
    TechinCategoryInstance,
    TechinRuleInstance,
    TechinSubCategoryInstance,
)
from .permissions import judge_required, user_can_access_team


# 1 = A Team, 2 = X Team. Mirrors teams.team_class_id and
# rule_category_instances.team_class_id.
TEAM_CLASSES = [
    {"id": 1, "slug": "a", "label": "A Team"},
    {"id": 2, "slug": "x", "label": "X Team"},
]


def _team_class_from_request(request):
    """Resolve the requested team class from the ?class= query param (default A)."""
    raw = (request.GET.get("class") or "a").lower()
    return 2 if raw in ("x", "2") else 1


def _team_class_slug(class_id):
    return "x" if class_id == 2 else "a"


def _resolve_rule_instance(event, rule_id):
    """Look up the TechinRuleInstance for a given event + global rule id."""
    return get_object_or_404(
        TechinRuleInstance.objects.select_related(
            "rule",
            "subcategory_instance__rule_subcategory__category",
            "subcategory_instance__category_instance__rule_category",
        ),
        event=event,
        rule_id=rule_id,
    )


def _resolve_subcategory_instance(event, subcategory_id):
    return get_object_or_404(
        TechinSubCategoryInstance.objects.select_related(
            "rule_subcategory__category",
            "category_instance__rule_category",
        ),
        event=event,
        rule_subcategory_id=subcategory_id,
    )


def _resolve_category_instance(event, category_id):
    return get_object_or_404(
        TechinCategoryInstance.objects.select_related("rule_category"),
        event=event,
        rule_category_id=category_id,
    )

# @log_view
# @cache_page(300)
# def event_tech_in_overview(request):
#     # All rule categories become columns
#     categories = list(
#         RuleCategory.objects.all().order_by("rule_category_name")
#     )

#     # All tractors at events – one row per tractor/team
#     tractor_events = (
#         TractorEvent.objects
#         .filter(event_id=25,team__team_class=1)
#         .select_related("team", "event")
#         .order_by("event__event_name", "team__team_name")
#     )

#     rows = []
#     for te in tractor_events:
#         row = {
#             "tractor_event": te,
#             "team_name": te.team.team_name,
#             "event_name": te.event.event_name,
#             "category_values": [],
#         }

#         # For now, completion is hard-coded to 0%
#         for cat in categories:
#             row["category_values"].append({
#                 "category": cat,
#                 "percent_complete": 0,
#             })

#         rows.append(row)

#     context = {
#         "categories": categories,
#         "rows": rows,
#     }
#     return render(request, "tech_in/overview.html", context)

# @log_view
# def tech_in_team_detail(request, tractor_event_id):
#     """
#     Detail view for a single TractorEvent (team at an event).

#     Now groups rule statuses as:
#         Category → Subcategory → [rules]
#     so the template can render one big block per category.
#     """
#     key=request.get_full_path()
#     context=cache.get(key)
#     print(context)
#     if not context:
#         tractor_event = get_object_or_404(
#             TractorEvent.objects.select_related("team", "event"),
#             pk=tractor_event_id,
#         )

#         # Load all rule statuses for this tractor
#         rule_statuses = (
#             EventTractorRuleStatus.objects
#             .select_related(
#                 "rule",
#                 "rule__sub_category",
#                 "rule__sub_category__category",
#             )
#             .filter(event_tractor=tractor_event)
#             .order_by(
#                 "rule__sub_category__category__rule_category_name",
#                 "rule__sub_category__rule_subcategory_name",
#                 "rule__rule_id",
#             )
#         )

#         STATUS_MAP = {
#             0: ("Not Started", "status-not-started"),
#             1: ("Failed", "status-failed"),
#             2: ("Corrected", "status-corrected"),
#             3: ("Pass", "status-pass"),
#         }

#         # Build:
#         # categories[cat_id] = {
#         #   "category": <RuleCategory>,
#         #   "subcategories": OrderedDict({
#         #       subcat_id: {
#         #           "subcategory": <RuleSubCategory>,
#         #           "rules": [ { rule, status_label, status_class } ... ]
#         #       }
#         #   })
#         # }
#         categories = OrderedDict()

#         for rs in rule_statuses:
#             subcat = rs.rule.sub_category
#             cat = subcat.category

#             cat_id = cat.rule_category_id
#             subcat_id = subcat.rule_subcategory_id

#             if cat_id not in categories:
#                 categories[cat_id] = {
#                     "category": cat,
#                     "subcategories": OrderedDict(),
#                 }

#             if subcat_id not in categories[cat_id]["subcategories"]:
#                 categories[cat_id]["subcategories"][subcat_id] = {
#                     "subcategory": subcat,
#                     "rules": [],
#                 }

#             label, css_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))

#             categories[cat_id]["subcategories"][subcat_id]["rules"].append({
#                 "rule": rs.rule,
#                 "status": rs.status,
#                 "status_label": label,
#                 "status_class": css_class,
#             })

#         context = {
#             "tractor_event": tractor_event,
#             "team": tractor_event.team,
#             "event": tractor_event.event,
#             "categories": categories.values(),  # list of {category, subcategories}
#         }
#         cache.add(key,context)
#     if user_can_access_team(request.user,tractor_event):
#         return render(request, "tech_in/team_detail.html", context)
#     else:
#         return render(request, "tech_in/permission_denied.html", status=403)

def event_tech_in_overview(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    class_id = _team_class_from_request(request)

    category_insts = list(
        TechinCategoryInstance.objects
        .filter(event=event, released=True, team_class_id=class_id)
        .select_related("rule_category")
        .order_by("display_order", "rule_category__rule_category_name")
    )

    sub_insts = list(
        TechinSubCategoryInstance.objects
        .filter(event=event)
        .select_related("rule_subcategory")
    )
    subs_by_cat = {}
    for s in sub_insts:
        subs_by_cat.setdefault(s.category_instance_id, []).append(s)

    rule_insts = list(
        TechinRuleInstance.objects
        .filter(event=event)
        .only("rule_instance_id", "subcategory_instance_id")
    )
    rules_by_sub = {}
    rule_inst_ids_by_cat = {}
    for r in rule_insts:
        rules_by_sub.setdefault(r.subcategory_instance_id, []).append(r.rule_instance_id)
    for cat_inst in category_insts:
        ids = []
        for s in subs_by_cat.get(cat_inst.rule_category_instance_id, []):
            ids.extend(rules_by_sub.get(s.rule_subcategory_instance_id, []))
        rule_inst_ids_by_cat[cat_inst.rule_category_instance_id] = ids

    tractor_events = list(
        TractorEvent.objects
        .filter(event=event, team__team_class=class_id)
        .select_related("team", "event")
        .order_by("team__team_name")
    )

    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor__in=tractor_events)
        .values_list("event_tractor_id", "rule_instance_id", "status")
    )
    status_by_te_rule_inst = {(te_id, ri_id): status for te_id, ri_id, status in statuses_qs}

    def is_complete(status_value):
        return status_value in (2, 3)

    rows = []
    for te in tractor_events:
        row = {
            "tractor_event": te,
            "team_name": te.team.team_name,
            "event_name": te.event.event_name,
            "category_values": [],
        }
        for cat_inst in category_insts:
            ri_ids = rule_inst_ids_by_cat.get(cat_inst.rule_category_instance_id, [])
            total = len(ri_ids)
            done = sum(
                1 for ri_id in ri_ids
                if is_complete(status_by_te_rule_inst.get((te.pk, ri_id)))
            )
            percent = round((done / total) * 100) if total else 0
            row["category_values"].append({
                "category": cat_inst,
                "percent_complete": percent,
            })
        rows.append(row)

    context = {
        "event": event,
        "categories": category_insts,
        "rows": rows,
        "team_class_id": class_id,
        "team_class_slug": _team_class_slug(class_id),
        "team_classes": TEAM_CLASSES,
    }
    return render(request, "tech_in/overview.html", context)

def subcategory_detail(request, event_id, subcategory_id):
    """Shows one subcategory's rule instances for this event."""
    event = get_object_or_404(Event, pk=event_id)
    sub_inst = _resolve_subcategory_instance(event, subcategory_id)

    rule_insts = list(
        TechinRuleInstance.objects
        .filter(event=event, subcategory_instance=sub_inst)
        .select_related("rule")
        .order_by("display_order", "rule__rule_id")
    )

    cat_inst = sub_inst.category_instance or _resolve_category_instance(
        event, sub_inst.rule_subcategory.category_id
    )

    context = {
        "event": event,
        "subcategory": sub_inst,
        "category": cat_inst,
        "rules": rule_insts,
    }
    return render(request, "tech_in/subcategory_detail.html", context)

def rule_detail(request, event_id, rule_id):
    """Shows a single rule instance with all team statuses for this event."""
    event = get_object_or_404(Event, pk=event_id)
    rule_inst = _resolve_rule_instance(event, rule_id)

    statuses = (
        EventTractorRuleStatus.objects
        .select_related("event_tractor__team")
        .filter(rule_instance=rule_inst)
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
            "images": [],
            "comments": [],
        })

    sub_inst = rule_inst.subcategory_instance
    cat_inst = sub_inst.category_instance if sub_inst else None

    context = {
        "event": event,
        "rule": rule_inst,
        "subcategory": sub_inst,
        "category": cat_inst,
        "status_rows": status_rows,
    }
    return render(request, "tech_in/rule_detail.html", context)

def team_tech_overview(request, event_id, team_id):
    
    team = get_object_or_404(Team, pk=team_id)

    if not user_can_access_team(request.user,team):
        return render(request,"tech_in/permission_denied.html")

    key=request.get_full_path()
    ren=cache.get(key)
    if not ren:

        
        event = get_object_or_404(Event, pk=event_id)
        if not event.techin_released:
            raise Http404("Page not found")
        te = get_object_or_404(
            TractorEvent.objects.select_related("team", "event"),
            team=team,
            event=event,
        )

        category_insts = list(
            TechinCategoryInstance.objects
            .filter(event=event, released=True, team_class_id=team.team_class_id)
            .select_related("rule_category")
            .order_by("display_order", "rule_category__rule_category_name")
        )
        sub_insts = list(
            TechinSubCategoryInstance.objects
            .filter(event=event)
            .select_related("rule_subcategory")
            .order_by("display_order", "rule_subcategory__rule_subcategory_name")
        )
        subs_by_cat = {}
        for s in sub_insts:
            subs_by_cat.setdefault(s.category_instance_id, []).append(s)

        rule_insts = list(
            TechinRuleInstance.objects
            .filter(event=event)
            .only("rule_instance_id", "subcategory_instance_id")
        )
        rule_ids_by_sub = {}
        for r in rule_insts:
            rule_ids_by_sub.setdefault(r.subcategory_instance_id, []).append(r.rule_instance_id)

        status_by_rule_inst_id = dict(
            EventTractorRuleStatus.objects
            .filter(event_tractor=te)
            .values_list("rule_instance_id", "status")
        )

        def is_complete(status_value):
            return status_value in (2, 3)

        category_rows = []
        for cat_inst in category_insts:
            cat_total = 0
            cat_done = 0
            sub_rows = []
            for sub_inst in subs_by_cat.get(cat_inst.rule_category_instance_id, []):
                ri_ids = rule_ids_by_sub.get(sub_inst.rule_subcategory_instance_id, [])
                total = len(ri_ids)
                done = sum(
                    1 for ri_id in ri_ids
                    if is_complete(status_by_rule_inst_id.get(ri_id))
                )
                cat_total += total
                cat_done += done
                sub_percent = round((done / total) * 100) if total else 0
                sub_rows.append({
                    "subcategory": sub_inst,
                    "percent_complete": sub_percent,
                })
            cat_percent = round((cat_done / cat_total) * 100) if cat_total else 0
            category_rows.append({
                "category": cat_inst,
                "percent_complete": cat_percent,
                "subcategories": sub_rows,
            })

        context = {
            "event": event,
            "tractor_event": te,
            "team": te.team,
            "category_rows": category_rows,
        }
        ren=render(request, "tech_in/team_tech_overview.html", context)
        cache.add(key,ren)
    
    return ren
         #return render(request, "tech_in/team_tech_overview.html", context)

def team_subcategory_detail(request, event_id, team_id, subcategory_id):
    team = get_object_or_404(Team,pk=team_id)

    if not user_can_access_team(request.user,team):
        return render(request,"tech_in/permission_denied.html")

    key=request.get_full_path()
    ren=cache.get(key)

    if not ren:
        event = get_object_or_404(Event, pk=event_id)
        if not event.techin_released:
            raise Http404("Page not found")
        te = get_object_or_404(
            TractorEvent.objects.select_related("team", "event"),
            team=team,
            event=event,
        )
        sub_inst = _resolve_subcategory_instance(event, subcategory_id)

        rule_insts = list(
            TechinRuleInstance.objects
            .filter(event=event, subcategory_instance=sub_inst)
            .select_related("rule")
            .order_by("display_order", "rule__rule_id")
        )

        statuses_qs = (
            EventTractorRuleStatus.objects
            .filter(event_tractor=te, rule_instance__in=rule_insts)
        )
        status_by_ri_id = {rs.rule_instance_id: rs for rs in statuses_qs}

        STATUS_MAP = {
            0: ("Not Started", "status-not-started"),
            1: ("Failed", "status-failed"),
            2: ("Corrected", "status-corrected"),
            3: ("Pass", "status-pass"),
        }

        rule_rows = []
        for ri in rule_insts:
            rs = status_by_ri_id.get(ri.rule_instance_id)
            if rs:
                label, css_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))
            else:
                label, css_class = ("Not Started", "status-not-started")
                rs = None
            rule_rows.append({
                "rule": ri,
                "status_label": label,
                "status_class": css_class,
                "status_obj": rs,
            })

        cat_inst = sub_inst.category_instance or _resolve_category_instance(
            event, sub_inst.rule_subcategory.category_id
        )

        context = {
            "event": event,
            "tractor_event": te,
            "team": te.team,
            "subcategory": sub_inst,
            "category": cat_inst,
            "rule_rows": rule_rows,
        }
        ren=render(request, "tech_in/team_subcategory_detail.html", context)
        cache.add(key,ren)
    return ren

def team_rule_detail(request, event_id, team_id, rule_id):
    team = get_object_or_404(Team,pk=team_id)
    if not user_can_access_team(request.user,team):
        return render(request,"tech_in/permission_denied.html")
    event = get_object_or_404(Event, pk=event_id)
    if not event.techin_released:
        raise Http404("Page not found")
    te = get_object_or_404(
        TractorEvent.objects.select_related("team", "event"),
        team=team,
        event=event,
    )
    rule_inst = _resolve_rule_instance(event, rule_id)

    rs = EventTractorRuleStatus.objects.filter(
        event_tractor=te,
        rule_instance=rule_inst,
    ).first()
    #print(rs.event_tractor_rule_status_id)
    STATUS_MAP = {
        0: ("Not Started", "status-not-started"),
        1: ("Failed", "status-failed"),
        2: ("Corrected", "status-corrected"),
        3: ("Pass", "status-pass"),
    }
    if rs:
        comments=rs.media.filter(media_type=RuleTractorMedia.types.COMMENT).all()
        images=rs.media.filter(media_type=RuleTractorMedia.types.IMAGE).all()
    else:
        comments=[]
        images=[]
    if rs:
        status_label, status_class = STATUS_MAP.get(rs.status, ("Unknown", "status-unknown"))
    else:
        status_label, status_class = ("Not Started", "status-not-started")
    sub_inst = rule_inst.subcategory_instance
    cat_inst = sub_inst.category_instance if sub_inst else None
    context = {
        "comments":comments,
        "images":images,
        "event": event,
        "tractor_event": te,
        "team": te.team,
        "rule": rule_inst,
        "subcategory": sub_inst,
        "category": cat_inst,
        "status_obj": rs,
        "status_label": status_label,
        "status_class": status_class,
    }
    return render(request, "tech_in/team_rule_detail.html", context)

def category_view(request,event_id,category_id):
    event=get_object_or_404(Event,pk=event_id)
    cat_inst = _resolve_category_instance(event, category_id)
    rts=EventTractorRuleStatus.objects.filter(
        event_tractor__event=event,
        rule_instance__subcategory_instance__category_instance=cat_inst,
    ).all()
    #print(rts)
    context={}
    return render(request,"tech_in/permission_denied.html",context)


# ---------------------------------------------------------------------------
# Judge views
# ---------------------------------------------------------------------------

STATUS_CHOICES = [(3, "Pass"), (1, "Fail"), (2, "Corrected"), (0, "Not Started")]


@judge_required
def judge_event_overview(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    class_id = _team_class_from_request(request)
    category_insts = list(
        TechinCategoryInstance.objects
        .filter(event=event, released=True, team_class_id=class_id)
        .select_related("rule_category")
        .order_by("display_order", "rule_category__rule_category_name")
    )
    return render(request, "tech_in/judge/event_overview.html", {
        "event": event,
        "categories": category_insts,
        "team_class_id": class_id,
        "team_class_slug": _team_class_slug(class_id),
        "team_classes": TEAM_CLASSES,
    })


@judge_required
def judge_category_teams(request, event_id, category_id):
    event = get_object_or_404(Event, pk=event_id)
    cat_inst = _resolve_category_instance(event, category_id)

    rule_inst_ids = list(
        TechinRuleInstance.objects
        .filter(event=event, subcategory_instance__category_instance=cat_inst)
        .values_list("rule_instance_id", flat=True)
    )
    total = len(rule_inst_ids)

    tractor_events = (
        TractorEvent.objects
        .filter(event=event, team__team_class=cat_inst.team_class_id)
        .select_related("team")
        .order_by("team__team_name")
    )

    completed_by_te = dict(
        EventTractorRuleStatus.objects
        .filter(
            event_tractor__in=tractor_events,
            rule_instance_id__in=rule_inst_ids,
            status__in=(2, 3),
        )
        .values("event_tractor_id")
        .annotate(n=Count("event_tractor_rule_status_id"))
        .values_list("event_tractor_id", "n")
    )

    team_rows = []
    for te in tractor_events:
        completed = completed_by_te.get(te.pk, 0)
        percent = round((completed / total) * 100) if total else 0
        team_rows.append({
            "tractor_event": te,
            "team": te.team,
            "completed": completed,
            "total": total,
            "percent": percent,
        })

    return render(request, "tech_in/judge/category_teams.html", {
        "event": event,
        "category": cat_inst,
        "team_rows": team_rows,
    })


@judge_required
def judge_team_subcategories(request, event_id, category_id, team_id):
    event = get_object_or_404(Event, pk=event_id)
    cat_inst = _resolve_category_instance(event, category_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)

    sub_insts = list(
        TechinSubCategoryInstance.objects
        .filter(event=event, category_instance=cat_inst)
        .select_related("rule_subcategory")
        .order_by("display_order", "rule_subcategory__rule_subcategory_name")
    )

    ri_counts_by_sub = dict(
        TechinRuleInstance.objects
        .filter(event=event, subcategory_instance__in=sub_insts)
        .values("subcategory_instance_id")
        .annotate(n=Count("rule_instance_id"))
        .values_list("subcategory_instance_id", "n")
    )

    completed_by_sub = dict(
        EventTractorRuleStatus.objects
        .filter(
            event_tractor=te,
            rule_instance__subcategory_instance__in=sub_insts,
            status__in=(2, 3),
        )
        .values("rule_instance__subcategory_instance_id")
        .annotate(n=Count("event_tractor_rule_status_id"))
        .values_list("rule_instance__subcategory_instance_id", "n")
    )

    subcat_rows = []
    for sub_inst in sub_insts:
        total = ri_counts_by_sub.get(sub_inst.rule_subcategory_instance_id, 0)
        completed = completed_by_sub.get(sub_inst.rule_subcategory_instance_id, 0)
        percent = round((completed / total) * 100) if total else 0
        subcat_rows.append({
            "subcategory": sub_inst,
            "completed": completed,
            "total": total,
            "percent": percent,
        })

    return render(request, "tech_in/judge/team_subcategories.html", {
        "event": event,
        "category": cat_inst,
        "team": team,
        "tractor_event": te,
        "subcat_rows": subcat_rows,
    })


@judge_required
def judge_subcategory_rules(request, event_id, category_id, team_id, subcategory_id):
    event = get_object_or_404(Event, pk=event_id)
    cat_inst = _resolve_category_instance(event, category_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)
    sub_inst = _resolve_subcategory_instance(event, subcategory_id)

    rule_insts = list(
        TechinRuleInstance.objects
        .filter(event=event, subcategory_instance=sub_inst)
        .select_related("rule")
        .order_by("display_order", "rule__rule_id")
    )

    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor=te, rule_instance__in=rule_insts)
        .prefetch_related("media")
    )
    status_by_ri = {rs.rule_instance_id: rs for rs in statuses_qs}

    rule_rows = []
    for ri in rule_insts:
        rs = status_by_ri.get(ri.rule_instance_id)
        if rs:
            status_val = rs.status
            status_id = rs.pk
            comment_obj = next(
                (m for m in rs.media.all() if m.media_type == RuleTractorMedia.types.COMMENT),
                None,
            )
            comment = comment_obj.media if comment_obj else ""
        else:
            status_val = 0
            status_id = None
            comment = ""
        rule_rows.append({
            "rule": ri,
            "status": status_val,
            "status_id": status_id,
            "comment": comment,
        })

    return render(request, "tech_in/judge/subcategory_rules.html", {
        "event": event,
        "category": cat_inst,
        "team": team,
        "tractor_event": te,
        "subcategory": sub_inst,
        "rule_rows": rule_rows,
        "status_choices": STATUS_CHOICES,
        "url_update_status": "/techin/judge/ajax/update-status/",
        "url_update_comment": "/techin/judge/ajax/update-comment/",
    })


@judge_required
def judge_rule_photos(request, event_id, category_id, team_id, rule_id):
    event = get_object_or_404(Event, pk=event_id)
    cat_inst = _resolve_category_instance(event, category_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)
    rule_inst = _resolve_rule_instance(event, rule_id)

    rs, _ = EventTractorRuleStatus.objects.get_or_create(
        event_tractor=te, rule_instance=rule_inst, defaults={"status": 0}
    )
    photos = rs.media.filter(media_type=RuleTractorMedia.types.IMAGE).order_by("id")

    return render(request, "tech_in/judge/rule_photos.html", {
        "event": event,
        "category": cat_inst,
        "team": team,
        "tractor_event": te,
        "rule": rule_inst,
        "status_obj": rs,
        "photos": photos,
        "subcategory": rule_inst.subcategory_instance,
    })


# ---------------------------------------------------------------------------
# Judge AJAX endpoints
# ---------------------------------------------------------------------------

@judge_required
@require_POST
def judge_update_status(request):
    try:
        data = json.loads(request.body)
        event_id = int(data["event_id"])
        team_id = int(data["team_id"])
        rule_id = int(data["rule_id"])
        status = int(data["status"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid request"}, status=400)

    if status not in (0, 1, 2, 3):
        return JsonResponse({"error": "Invalid status"}, status=400)

    event = get_object_or_404(Event, pk=event_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)
    rule_inst = _resolve_rule_instance(event, rule_id)

    with transaction.atomic():
        rs, created = (
            EventTractorRuleStatus.objects
            .select_for_update()
            .get_or_create(
                event_tractor=te,
                rule_instance=rule_inst,
                defaults={"status": status},
            )
        )
        if not created:
            rs.status = status
            rs.save(update_fields=["status"])

    return JsonResponse({"ok": True, "status_id": rs.pk, "status": rs.status})


@judge_required
@require_POST
def judge_update_comment(request):
    try:
        data = json.loads(request.body)
        status_id = int(data["status_id"])
        comment_text = str(data.get("comment", ""))
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid request"}, status=400)

    rs = get_object_or_404(EventTractorRuleStatus, pk=status_id)

    with transaction.atomic():
        existing = (
            RuleTractorMedia.objects
            .select_for_update()
            .filter(event_tractor_rule_status=rs, media_type=RuleTractorMedia.types.COMMENT)
            .first()
        )
        if existing:
            existing.media = comment_text
            existing.save(update_fields=["media"])
            media_id = existing.pk
        else:
            obj = RuleTractorMedia.objects.create(
                event_tractor_rule_status=rs,
                media_type=RuleTractorMedia.types.COMMENT,
                media=comment_text,
            )
            media_id = obj.pk

    return JsonResponse({"ok": True, "media_id": media_id})


@judge_required
@require_POST
def judge_upload_photo(request):
    try:
        status_id = int(request.POST["status_id"])
    except (KeyError, ValueError):
        return JsonResponse({"error": "Missing status_id"}, status=400)

    photo = request.FILES.get("photo")
    if not photo:
        return JsonResponse({"error": "No photo provided"}, status=400)

    ext = photo.name.rsplit(".", 1)[-1].lower() if "." in photo.name else ""
    if ext not in {"png", "jpg", "jpeg", "gif", "webp"}:
        return JsonResponse({"error": "Invalid file type"}, status=400)

    rs = get_object_or_404(EventTractorRuleStatus, pk=status_id)

    safe_root = re.sub(r"[^\w]", "_", photo.name.rsplit(".", 1)[0])[:50]
    filename = (
        f"techin_event{rs.event_tractor.event_id}"
        f"_team{rs.event_tractor.team_id}"
        f"_ruleinst{rs.rule_instance_id}"
        f"_{safe_root}.{ext}"
    )
    rel_path = f"techin/photos/{filename}"
    from iqs_site.storage import MediaStorage
    storage = MediaStorage()
    storage.save(rel_path, photo)
    obj = RuleTractorMedia.objects.create(
        event_tractor_rule_status=rs,
        media_type=RuleTractorMedia.types.IMAGE,
        media=rel_path,
    )

    return JsonResponse({"ok": True, "media_id": obj.pk, "url": settings.MEDIA_URL + rel_path})


@judge_required
@require_POST
def judge_delete_media(request, media_id):
    media = get_object_or_404(RuleTractorMedia, pk=media_id)
    if media.media_type == RuleTractorMedia.types.IMAGE:
        Path(settings.MEDIA_ROOT, media.media).unlink(missing_ok=True)
    media.delete()
    return JsonResponse({"ok": True})