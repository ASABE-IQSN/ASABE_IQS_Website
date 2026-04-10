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

from .models import EventTractorRuleStatus, Rule, RuleCategory, RuleSubCategory, RuleTractorMedia
from .permissions import judge_required, user_can_access_team

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

    # All categories with their subcategories & rules
    categories = list(
        RuleCategory.objects
        .prefetch_related("subcategories__rules")
        .order_by("rule_category_name")
    )

    # All tractor-events (teams) for this event
    tractor_events = list(
        TractorEvent.objects
        .filter(event=event,team__team_class=1)
        .select_related("team", "event")
        .order_by("team__team_name")
    )

    # All statuses for these tractor-events, indexed by (tractor_event_id, rule_id)
    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor__in=tractor_events)
        .select_related("rule")
    )
    status_by_te_rule = {
        (rs.event_tractor_id, rs.rule.rule_id): rs.status
        for rs in statuses_qs
    }

    def is_complete(status_value: int | None) -> bool:
        # Pass (3) or Corrected (2) count as "complete"
        return status_value in (2, 3)

    rows = []

    for te in tractor_events:
        row = {
            "tractor_event": te,
            "team_name": te.team.team_name,
            "event_name": te.event.event_name,
            "category_values": [],
        }

        for cat in categories:
            total_rules = 0
            completed_rules = 0

            # all rules in this category (via subcategories)
            for subcat in cat.subcategories.all():
                for rule in subcat.rules.all():
                    total_rules += 1
                    status_value = status_by_te_rule.get((te.pk, rule.rule_id))
                    if is_complete(status_value):
                        completed_rules += 1

            if total_rules > 0:
                percent = round((completed_rules / total_rules) * 100)
            else:
                percent = 0

            row["category_values"].append({
                "category": cat,
                "percent_complete": percent,
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

        # Pull all categories, and for each category prefetch its subcategories and rules
        categories = (
            RuleCategory.objects
            .prefetch_related("subcategories__rules")
            .order_by("rule_category_name")
        )

        # All statuses for this tractor/event, indexed by rule_id for quick lookup
        statuses_qs = (
            EventTractorRuleStatus.objects
            .filter(event_tractor=te)
            .select_related("rule")
        )
        status_by_rule_id = {rs.rule.rule_id: rs.status for rs in statuses_qs}

        def is_complete(status_value: int | None) -> bool:
            # Pass (3) or Corrected (2) count as "complete"
            return status_value in (2, 3)

        category_rows = []

        for cat in categories:
            cat_total_rules = 0
            cat_completed_rules = 0
            sub_rows = []

            for subcat in cat.subcategories.all():
                rules = list(subcat.rules.all())
                total_rules = len(rules)
                completed_rules = 0

                for rule in rules:
                    status_value = status_by_rule_id.get(rule.rule_id)
                    if is_complete(status_value):
                        completed_rules += 1

                # Update category-level counts
                cat_total_rules += total_rules
                cat_completed_rules += completed_rules

                if total_rules > 0:
                    sub_percent = round((completed_rules / total_rules) * 100)
                else:
                    sub_percent = 0

                sub_rows.append({
                    "subcategory": subcat,
                    "percent_complete": sub_percent,
                })

            if cat_total_rules > 0:
                cat_percent = round((cat_completed_rules / cat_total_rules) * 100)
            else:
                cat_percent = 0

            category_rows.append({
                "category": cat,
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
    rule = get_object_or_404(
        Rule.objects.select_related("sub_category__category"),
        pk=rule_id,
    )

    rs = EventTractorRuleStatus.objects.filter(
        event_tractor=te,
        rule=rule,
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
    context = {
        "comments":comments,
        "images":images,
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
    #print(rs.event_tractor_rule_status_id)
    return render(request, "tech_in/team_rule_detail.html", context)

def category_view(request,event_id,category_id):
    category=get_object_or_404(RuleCategory,pk=category_id)
    event=get_object_or_404(Event,pk=event_id)
    rts=EventTractorRuleStatus.objects.filter(event_tractor__event=event,rule__sub_category__category=category).all()
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
    categories = list(RuleCategory.objects.order_by("rule_category_name"))
    return render(request, "tech_in/judge/event_overview.html", {
        "event": event,
        "categories": categories,
    })


@judge_required
def judge_category_teams(request, event_id, category_id):
    event = get_object_or_404(Event, pk=event_id)
    category = get_object_or_404(RuleCategory, pk=category_id)

    rules_in_cat = list(
        Rule.objects.filter(sub_category__category=category).values_list("rule_id", flat=True)
    )
    total = len(rules_in_cat)

    tractor_events = (
        TractorEvent.objects
        .filter(event=event, team__team_class=1)
        .select_related("team")
        .order_by("team__team_name")
    )

    # Aggregate completed (status 2 or 3) counts per tractor_event
    completed_by_te = dict(
        EventTractorRuleStatus.objects
        .filter(event_tractor__in=tractor_events, rule_id__in=rules_in_cat, status__in=(2, 3))
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
        "category": category,
        "team_rows": team_rows,
    })


@judge_required
def judge_team_subcategories(request, event_id, category_id, team_id):
    event = get_object_or_404(Event, pk=event_id)
    category = get_object_or_404(RuleCategory, pk=category_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)

    subcategories = list(
        RuleSubCategory.objects.filter(category=category)
        .prefetch_related("rules")
        .order_by("rule_subcategory_name")
    )

    # All completed statuses for this TE in this category
    completed_by_subcat = dict(
        EventTractorRuleStatus.objects
        .filter(event_tractor=te, rule__sub_category__category=category, status__in=(2, 3))
        .values("rule__sub_category_id")
        .annotate(n=Count("event_tractor_rule_status_id"))
        .values_list("rule__sub_category_id", "n")
    )

    subcat_rows = []
    for subcat in subcategories:
        rules = list(subcat.rules.all())
        total = len(rules)
        completed = completed_by_subcat.get(subcat.pk, 0)
        percent = round((completed / total) * 100) if total else 0
        subcat_rows.append({
            "subcategory": subcat,
            "completed": completed,
            "total": total,
            "percent": percent,
        })

    return render(request, "tech_in/judge/team_subcategories.html", {
        "event": event,
        "category": category,
        "team": team,
        "tractor_event": te,
        "subcat_rows": subcat_rows,
    })


@judge_required
def judge_subcategory_rules(request, event_id, category_id, team_id, subcategory_id):
    event = get_object_or_404(Event, pk=event_id)
    category = get_object_or_404(RuleCategory, pk=category_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)
    subcategory = get_object_or_404(RuleSubCategory, pk=subcategory_id, category=category)

    rules = list(Rule.objects.filter(sub_category=subcategory).order_by("rule_id"))

    statuses_qs = (
        EventTractorRuleStatus.objects
        .filter(event_tractor=te, rule__in=rules)
        .prefetch_related("media")
    )
    status_by_rule = {rs.rule_id: rs for rs in statuses_qs}

    rule_rows = []
    for rule in rules:
        rs = status_by_rule.get(rule.pk)
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
            "rule": rule,
            "status": status_val,
            "status_id": status_id,
            "comment": comment,
        })

    return render(request, "tech_in/judge/subcategory_rules.html", {
        "event": event,
        "category": category,
        "team": team,
        "tractor_event": te,
        "subcategory": subcategory,
        "rule_rows": rule_rows,
        "status_choices": STATUS_CHOICES,
        "url_update_status": "/techin/judge/ajax/update-status/",
        "url_update_comment": "/techin/judge/ajax/update-comment/",
    })


@judge_required
def judge_rule_photos(request, event_id, category_id, team_id, rule_id):
    event = get_object_or_404(Event, pk=event_id)
    category = get_object_or_404(RuleCategory, pk=category_id)
    team = get_object_or_404(Team, pk=team_id)
    te = get_object_or_404(TractorEvent, event=event, team=team)
    rule = get_object_or_404(Rule, pk=rule_id, sub_category__category=category)

    rs, _ = EventTractorRuleStatus.objects.get_or_create(
        event_tractor=te, rule=rule, defaults={"status": 0}
    )
    photos = rs.media.filter(media_type=RuleTractorMedia.types.IMAGE).order_by("id")

    return render(request, "tech_in/judge/rule_photos.html", {
        "event": event,
        "category": category,
        "team": team,
        "tractor_event": te,
        "rule": rule,
        "status_obj": rs,
        "photos": photos,
        "subcategory": rule.sub_category,
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
    rule = get_object_or_404(Rule, pk=rule_id)

    with transaction.atomic():
        rs, created = (
            EventTractorRuleStatus.objects
            .select_for_update()
            .get_or_create(event_tractor=te, rule=rule, defaults={"status": status})
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
        f"_rule{rs.rule_id}"
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