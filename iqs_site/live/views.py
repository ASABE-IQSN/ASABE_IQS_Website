from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils import timezone
import datetime
from events.models import (
    Team, Event, EventTeam, Hook, Pull,
    TractorEvent, ManeuverabilityRun, DurabilityRun,
)
from techin.models import RuleCategory, EventTractorRuleStatus
from schedule.models import ScheduleItem
from django.conf import settings
from compforms.models import OverlayScene
import json
# Create your views here.


# ── Live landing helpers ───────────────────────────────────────────────────────

LEADERBOARD_LIMIT = 10
RUNS_LIMIT = 8


def _leaderboard(event):
    pulls = (
        Pull.objects
        .select_related("team", "team__team_class", "hook")
        .filter(event=event, final_distance__isnull=False)
        .order_by("-final_distance")[:LEADERBOARD_LIMIT]
    )
    return [
        {
            "team_name": p.team.team_name if p.team else "",
            "team_number": p.team.team_number if p.team else "",
            "hook_name": (p.hook.hook_name if p.hook and p.hook.hook_name
                          else (f"Hook {p.hook_id}" if p.hook_id else "")),
            "distance": round(p.final_distance, 2) if p.final_distance is not None else None,
            "team_class": p.team.team_class.name if (p.team and p.team.team_class) else "",
        }
        for p in pulls
    ]


def _current_pull(event):
    p = (
        Pull.objects
        .select_related("team", "hook")
        .filter(event=event, state=Pull.States.RUNNING)
        .first()
    )
    if not p:
        return None
    return {
        "team_name": p.team.team_name if p.team else "",
        "hook_name": (p.hook.hook_name if p.hook and p.hook.hook_name
                      else (f"Hook {p.hook_id}" if p.hook_id else "")),
    }


def _run_summary(qs, fields):
    """Build a list of dicts from a ManeuverabilityRun/DurabilityRun queryset.

    fields: list of model attributes to include in addition to team/state/run_order.
    """
    out = []
    for r in qs:
        row = {
            "team_name": r.team.team_name if r.team_id else "",
            "team_number": r.team.team_number if r.team_id else "",
            "run_order": r.run_order,
            "state": r.state,
        }
        for f in fields:
            row[f] = getattr(r, f, None)
        out.append(row)
    return out


def _maneuverability_summary(event):
    qs = (
        ManeuverabilityRun.objects
        .select_related("team")
        .filter(event=event)
        .exclude(state="SCRATCHED")
        .order_by("-state", "run_order")[:RUNS_LIMIT]
    )
    return _run_summary(qs, [])


def _durability_summary(event):
    qs = (
        DurabilityRun.objects
        .select_related("team")
        .filter(event=event)
        .exclude(state="SCRATCHED")
        .order_by("-state", "run_order")[:RUNS_LIMIT]
    )
    return _run_summary(qs, ["total_laps"])


def _tech_status(event):
    """One overall % per team across all rules (Pass=3 or Corrected=2 → complete)."""
    tractor_events = list(
        TractorEvent.objects
        .filter(event=event, team__team_class=1)
        .select_related("team")
        .order_by("team__team_name")
    )
    if not tractor_events:
        return []

    total_rules = 0
    for cat in RuleCategory.objects.prefetch_related("subcategories__rules"):
        for sub in cat.subcategories.all():
            total_rules += sub.rules.count()
    if total_rules == 0:
        return []

    complete_by_te = {}
    for rs in (
        EventTractorRuleStatus.objects
        .filter(event_tractor__in=tractor_events, status__in=(2, 3))
        .values_list("event_tractor_id", flat=True)
    ):
        complete_by_te[rs] = complete_by_te.get(rs, 0) + 1

    rows = []
    for te in tractor_events:
        done = complete_by_te.get(te.pk, 0)
        rows.append({
            "team_name": te.team.team_name,
            "team_number": te.team.team_number,
            "percent": round(done / total_rules * 100) if total_rules else 0,
        })
    return rows


def _classify_schedule_type(name: str) -> str:
    n = (name or "").lower()
    if "design" in n:
        return "dod"
    if "presentation" in n:
        return "presentation"
    return "general"


def _resolve_today(request):
    """Allow ?date=YYYY-MM-DD to override 'today' for DEBUG or staff testing."""
    date_str = request.GET.get("date")
    if date_str and (settings.DEBUG or request.user.is_staff):
        try:
            return datetime.date.fromisoformat(date_str)
        except ValueError:
            pass
    return timezone.localdate()


def _schedule_today(event, today):
    items = (
        ScheduleItem.objects
        .select_related("type", "team", "location")
        .filter(event=event, datetime__date=today)
        .order_by("datetime")
    )
    general, dod, pres = [], [], []
    for it in items:
        bucket = _classify_schedule_type(it.type.name if it.type_id else "")
        row = {
            "time": timezone.localtime(it.datetime).strftime("%H:%M") if it.datetime else "",
            "name": it.name,
            "team_name": it.team.team_name if it.team_id else "",
            "location": it.location.name if it.location_id else "",
        }
        if bucket == "dod":
            dod.append(row)
        elif bucket == "presentation":
            pres.append(row)
        else:
            general.append(row)
    return general, dod, pres


def live_landing(request):
    event = Event.objects.filter(event_active=True).first()
    context = {
        "active_event": event,
        "api_url": settings.APIURL,
    }
    if event:
        today = _resolve_today(request)
        general, dod, pres = _schedule_today(event, today)
        context["schedule_date"] = today
        context["schedule_date_overridden"] = today != timezone.localdate()
        context.update({
            "leaderboard": _leaderboard(event),
            "current_pull": _current_pull(event),
            "maneuverability_summary": _maneuverability_summary(event),
            "durability_summary": _durability_summary(event),
            "tech_status": _tech_status(event),
            "schedule_today": general,
            "dod_today": dod,
            "presentations_today": pres,
            "last_updated": timezone.localtime().strftime("%H:%M:%S"),
        })
    return render(request, "live_landing.html", context)


def live_leaderboard_json(request):
    event = Event.objects.filter(event_active=True).first()
    if not event:
        return JsonResponse({"leaderboard": [], "current_pull": None})
    return JsonResponse({
        "leaderboard": _leaderboard(event),
        "current_pull": _current_pull(event),
    })


def live_runs_json(request):
    event = Event.objects.filter(event_active=True).first()
    if not event:
        return JsonResponse({"maneuverability": [], "durability": []})
    return JsonResponse({
        "maneuverability": _maneuverability_summary(event),
        "durability": _durability_summary(event),
    })


def live_techin_json(request):
    event = Event.objects.filter(event_active=True).first()
    if not event:
        return JsonResponse({"tech_status": []})
    return JsonResponse({"tech_status": _tech_status(event)})

def live_pull(request):
    context={}
    context["api_url"]=settings.APIURL
    return render(request,"live_pull.html",context)

def live_maneuverability(request):
    context = {}
    context["api_url"] = settings.APIURL
    return render(request, "live_maneuverability.html", context)

def live_durability(request):
    context = {}
    context["api_url"] = settings.APIURL
    return render(request, "live_durability.html", context)

def overlay(request):
    context = {"api_url": settings.APIURL}
    return render(request, "overlay.html", context)


@staff_member_required
def overlay_producer(request):
    context = {"api_url": settings.APIURL}
    return render(request, "overlay_producer.html", context)


@staff_member_required
def producer_pull(request):
    active_event = Event.objects.filter(event_active=True).first()
    hooks_data = []
    if active_event:
        hooks = Hook.objects.filter(event=active_event).order_by("start_time", "hook_id")
        for h in hooks:
            pulls = (
                Pull.objects.filter(hook=h)
                .select_related("team", "tractor")
                .order_by("run_order", "pull_id")
            )
            hooks_data.append({
                "hook_id": h.hook_id,
                "hook_name": h.hook_name or f"Hook {h.hook_id}",
                "pulls": [
                    {
                        "pull_id": p.pull_id,
                        "label": f"#{p.run_order} – {p.team.team_name} (pull {p.pull_id})",
                        "state": p.state,
                    }
                    for p in pulls
                ],
            })
    context = {
        "api_url": settings.APIURL,
        "active_event": active_event,
        "hooks_json": json.dumps(hooks_data),
    }
    return render(request, "producer_pull.html", context)


@staff_member_required
def announcer_pull(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_pull.html", context)


@staff_member_required
def announcer_maneuverability(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_maneuverability.html", context)


@staff_member_required
def announcer_durability(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_durability.html", context)


@staff_member_required
def overlay_scene_list(request):
    if request.method == 'POST':
        name = request.POST.get('name', 'New Scene').strip() or 'New Scene'
        canvas_width = int(request.POST.get('canvas_width', 1920))
        canvas_height = int(request.POST.get('canvas_height', 1080))
        scene = OverlayScene.objects.create(name=name, canvas_width=canvas_width, canvas_height=canvas_height)
        from django.shortcuts import redirect
        return redirect('live:overlay_scene_editor', scene_id=scene.scene_id)
    scenes = OverlayScene.objects.all().order_by('-updated_at')
    return render(request, 'overlay_scene_list.html', {'scenes': scenes})


@staff_member_required
def overlay_scene_editor(request, scene_id):
    from django.shortcuts import get_object_or_404
    scene = get_object_or_404(OverlayScene, pk=scene_id)
    scene_json = json.dumps({
        'name': scene.name,
        'canvas_width': scene.canvas_width,
        'canvas_height': scene.canvas_height,
        'elements': scene.elements,
    })
    return render(request, 'overlay_scene_editor.html', {
        'scene': scene,
        'scene_json': scene_json,
    })


@staff_member_required
def overlay_scene_save(request, scene_id):
    from django.shortcuts import get_object_or_404
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    scene = get_object_or_404(OverlayScene, pk=scene_id)
    try:
        data = json.loads(request.body)
        if 'name' in data:
            scene.name = data['name'].strip() or scene.name
        if 'elements' in data:
            scene.elements = data['elements']
        scene.save(update_fields=['name', 'elements', 'updated_at'])
        return JsonResponse({'ok': True, 'name': scene.name})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)