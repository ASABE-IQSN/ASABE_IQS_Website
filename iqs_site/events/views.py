from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.db.models import Prefetch
from collections import OrderedDict
from collections import defaultdict
import json
import os
from pathlib import Path
from .models import Event
from django.conf import settings
from .models import TeamClass, Team, PullMedia, TeamInfo, TractorInfo, EventTeamPhoto, EventTeam, Pull, Event, Hook, PullData, Tractor, TractorEvent, ScheduleItem, TractorMedia
from django.views.decorators.http import require_POST
from django.contrib import messages
from functools import wraps
from django.http import HttpRequest, HttpResponse
from iqs_site.utilities import log_view
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, render
from .models import Team, TeamInfo
from .permissions import can_edit_team
from django.core.exceptions import PermissionDenied
from .teaminfo_utils import INFO_MAP
from django.contrib.auth.decorators import login_required
from django.http import Http404
from .forms import TeamProfileEditForm
from django.db.models import OuterRef, Subquery


from .models import DurabilityRun, DurabilityData, ManeuverabilityRun, PerformanceEventMedia
from .models import Tractor, TractorInfo
from .forms import TractorProfileEditForm
from .permissions import can_edit_tractor
from .tractorinfo_utils import TRACTOR_INFO_MAP

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

@log_view
#@cache_page(300)  # 300 seconds = 5 minutes
@cache_page(300)  # 300 seconds = 5 minutes
def landing(request):
    now = timezone.now()  # timezone-aware; Django prefers this
    

    next_event = (
        Event.objects
        .filter(event_datetime__isnull=False)
        .filter(event_datetime__gte=now)
        .order_by("event_datetime")
        .prefetch_related("event_teams", "event_teams__team")  # rough equivalent of selectinload
        .first()
    )

    active_event=(
        Event.objects
        .filter(event_active=True)
        .first()
    )

    return render(request, "landing.html", {"next_event": next_event,"active_event":active_event,"active_page": "landing",})


@log_view
@cache_page(300)
def event_list(request):
    events = (
        Event.objects
        .all()
        .prefetch_related("event_teams__team")  # adjust related_name as needed
        .order_by("-event_datetime")
    )

    # first 2 classes – matches your original “first 2 team classes” behavior
    top_classes = list(TeamClass.objects.all()[:2])

    for event in events:
        # assuming `event_teams` is the related_name on EventTeam
        event_teams = list(event.event_teams.all())
        
        class_leaderboards = []
        for tc in top_classes:
            # filter all teams for this event in this class
            entries = [et for et in event_teams if et.team.team_class_id == tc.team_class_id]

            # sort by total_score descending (treat None as 0)
            entries.sort(key=lambda et: et.total_score or 0, reverse=True)

            if entries:
                class_leaderboards.append({
                    "team_class": tc,
                    "entries": entries[:3],  # top 3
                })

        event.class_leaderboards = class_leaderboards

    context = {
        "events": events,
        "top_classes": top_classes,
        "active_page": "events",
    }
    return render(request, "events/event_list.html", context)

@log_view
@cache_page(300)
def team_list(request):
    # Prefetch teams per class, sorted by name
    team_qs = Team.objects.order_by("team_name")

    team_classes = (
        TeamClass.objects
        .prefetch_related(
            Prefetch("teams", queryset=team_qs)
        )
        .order_by("name")
    )

    unclassified_teams = (
        Team.objects
        .filter(team_class__isnull=True)
        .order_by("team_name")
    )

    context = {
        "team_classes": team_classes,
        "unclassified_teams": unclassified_teams,
        "active_page": "teams",  # for nav highlighting in base.html
    }
    return render(request, "events/teams.html", context)


def health(request):
    return HttpResponse("ok")

@log_view
@cache_page(300)
def tractor_list(request):
    
    nickname_sq = TractorInfo.objects.filter(
    tractor_id=OuterRef("tractor_id"),
    info_type=TractorInfo.InfoTypes.NICKNAME,).values("info")[:1]
    tractors = Tractor.objects.select_related("original_team", "primary_photo").order_by("original_team","year").annotate(nickname_info=Subquery(nickname_sq))
    context = {
        "tractors": tractors,
        "active_page": "tractors",
    }
    return render(request, "events/tractor_list.html", context)

@log_view
@cache_page(300)
def privacy(request):
    return render(request, "events/privacy.html", {
        "active_page": None,  # or "privacy" if you want a nav link for it
        "contact_email":"asabeiqswebsite@gmail.com"
    })

@log_view
@cache_page(300)
def team_detail_page(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    # All event-team rows for this team (with events preloaded)
    event_teams = (
        EventTeam.objects
        .select_related("event", "team")
        .filter(team=team)
        .order_by("-event__event_datetime")
    )

    # Photos for this team (approved only), newest first
    team_photos = (
        EventTeamPhoto.objects
        .select_related("event_team__event")
        .filter(event_team__team=team, approved=True)
        .order_by("-event_team_photo_id")
    )

    instagram=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.INSTAGRAM).first()
    facebook=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.FACEBOOK).first()
    linkedin=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.LINKEDIN).first()
    bio=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.BIO).first()
    website=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.WEBSITE).first()
    youtube=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.YOUTUBE).first()
    nickname=TeamInfo.objects.filter(team=team,info_type=TeamInfo.InfoTypes.NICKNAME).first()

    # Build chart data from event_teams that have scores
    labels = []
    scores = []
    for et in event_teams:
        if et.total_score is not None and et.event:
            # Label: event name (you could also add date here)
            labels.append(et.event.event_name)
            scores.append(et.total_score)
    
    context = {
        "team": team,
        "event_teams": event_teams,
        "team_photos": team_photos,
        "chart_labels": labels,
        "chart_scores": scores,
        "chart_labels_json": json.dumps(labels),
        "chart_scores_json": json.dumps(scores),
        "active_page": "teams",
        "instagram":instagram,
        "facebook":facebook,
        "linkedin":linkedin,
        "bio":bio,
        "youtube":youtube,
        "website":website,
        "nickname":nickname
    }

    return render(request, "events/team_detail.html", context)

@log_view
@cache_page(300)
def team_event_detail(request, event_id, team_id):
    team = get_object_or_404(Team, pk=team_id)
    event = get_object_or_404(Event, pk=event_id)

    event_team = (
        EventTeam.objects
        .select_related("event", "team")
        .filter(event=event, team=team)
        .first()
    )

    # Top 3 standings for this event
    top3 = (
        EventTeam.objects
        .select_related("team")
        .filter(event=event)
        .order_by("-total_score")[:3]
    )
    team_in_top3 = any(et.team_id == team.team_id for et in top3)

    # Best pull overall in this event
    best_pull_overall = (
        Pull.objects
        .select_related("team", "hook")
        .filter(event=event, final_distance__isnull=False)
        .order_by("-final_distance")
        .first()
    )

    # Pulls for this team in this event
    pulls = (
        Pull.objects
        .select_related("hook")
        .filter(event=event, team=team)
        .order_by("hook__hook_name", "pull_id")
    )

    durability_runs = (
        DurabilityRun.objects
        .select_related("tractor")
        .filter(event=event, team=team)
        .order_by("run_order")
    )

    maneuverability_runs = (
        ManeuverabilityRun.objects
        .filter(event=event, team=team)
        .order_by("run_order")
    )
    
    schedule_items=(
        ScheduleItem.objects
        .select_related("type")
        .filter(event=event,team=team)
        .order_by("datetime"))

    # Chart data: labels = hook name / id, distances = final_distance (0 if None)
    chart_labels = []
    chart_distances = []
    for p in pulls:
        if p.hook and p.hook.hook_name:
            label = p.hook.hook_name
        else:
            label = f"Hook {p.hook_id}"
        chart_labels.append(label)
        chart_distances.append(p.final_distance or 0)

    # Event photos (approved only if you want)
    if event_team:
        event_photos = (
            EventTeamPhoto.objects
            .filter(event_team=event_team, approved=True)
            .order_by("event_team_photo_id")
        )
    else:
        event_photos = []

    context = {
        "team": team,
        "event": event,
        "event_team": event_team,
        "top3": top3,
        "team_in_top3": team_in_top3,
        "best_pull_overall": best_pull_overall,
        "pulls": pulls,
        "durability_runs": durability_runs,
        "maneuverability_runs": maneuverability_runs,
        "chart_labels_json": json.dumps(chart_labels),
        "chart_distances_json": json.dumps(chart_distances),
        "event_photos": event_photos,
        "active_page": "events",
        "schedule_items":schedule_items
    }
    return render(request, "events/team_event_detail.html", context)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@csrf_exempt
@require_POST
def upload_team_photo(request, event_id, team_id):
    print("Uploaded Photo")
    approved = False
    approved = request.user.is_authenticated and request.user.has_perm("events.can_auto_approve_team_photos")
    # Look up event & team so we can 404 nicely if bad IDs
    event = get_object_or_404(Event, pk=event_id)
    team = get_object_or_404(Team, pk=team_id)

    # Find EventTeam record
    event_team = (
        EventTeam.objects
        .filter(event=event, team=team)
        .first()
    )
    if event_team is None:
        # No matching EventTeam row
        return redirect("events:team_event_detail", event_id=event_id, team_id=team_id)

    # Check file presence
    file = request.FILES.get("photo")
    if not file or not file.name:
        return redirect("events:team_event_detail", event_id=event_id, team_id=team_id)

    # Client IP (respect X-Forwarded-For like in your Flask version)
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        ip = xff.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")

    filename = file.name

    if not allowed_file(filename):
        # Bad extension – just bounce back for now
        return redirect("events:team_event_detail", event_id=event_id, team_id=team_id)

    # Sanitize filename a bit
    name_root, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Optionally prefix with event/team to reduce collisions
    safe_root = "".join(c for c in name_root if c.isalnum() or c in ("-", "_"))
    if not safe_root:
        safe_root = "photo"

    filename = f"event{event_id}_team{team_id}_{safe_root}{ext}"

    # We'll mirror your Flask behavior:
    # Store under <project_root>/static/photos/<filename>
    # and save "photos/<filename>" in photo_path so {% static photo.photo_path %} works.
    static_root = None

    # For dev, STATICFILES_DIRS often has [ BASE_DIR / "static" ]
    static_dirs = getattr(settings, "STATICFILES_DIRS", [])
    if static_dirs:
        static_root = Path(static_dirs[0])
    else:
        # Fallback to BASE_DIR / "static"
        static_root = Path(settings.BASE_DIR) / "static"
    #static_root="/var/www/quarterscale/static"
    upload_dir = static_root / "photos"
    upload_dir.mkdir(parents=True, exist_ok=True)

    save_path = upload_dir / filename
    save_path=Path(f"/var/www/quarterscale/static/photos/{filename}")
    print(f"uploading to {save_path}")
    # Save the file to disk
    with save_path.open("wb+") as dest:
        for chunk in file.chunks():
            dest.write(chunk)
    print(f"Saved photo to {filename}")
    # Path relative to /static
    rel_path = f"photos/{filename}"

    # Create DB row; approved=False so you can moderate later if you want
    EventTeamPhoto.objects.create(
        event_team=event_team,
        photo_path=rel_path,
        submitted_from_ip=ip,
        approved=approved,
    )

    return redirect("events:team_event_detail", event_id=event_id, team_id=team_id)

@log_view
@cache_page(300)
def event_detail(request, event_id):
    event = get_object_or_404(
        Event.objects.select_related(),  # tweak as needed
        pk=event_id,
    )

    # Event teams with team + class info, sorted by total_score desc
    event_teams = list(
        event.event_teams.select_related("team__team_class").all()
    )
    event_teams.sort(key=lambda et: et.total_score or 0, reverse=True)

    # rankings_by_class: { "Comp A": [EventTeam, ...], "Comp B": [...] }
    rankings_by_class = OrderedDict()
    rankings_by_class["A Team"]=[]

    for et in event_teams:
        team_class = getattr(et.team, "team_class", None)
        class_name = team_class.name if team_class else "Unclassified"
        rankings_by_class.setdefault(class_name, []).append(et)

    # Hooks + pulls (sorted by final_distance desc)
    hooks_qs = (
        event.hooks
        .prefetch_related("pulls__team")
        .all()
    )

    schedule_items=(ScheduleItem.objects
                    .filter(event=event)
                    .order_by("datetime")
                    .filter(type=5)
    )

    event_hooks = []
    for hook in hooks_qs:
        pulls = list(hook.pulls.all())
        pulls.sort(key=lambda p: p.final_distance or 0, reverse=True)
        hook.pull_entries = pulls
        hook.best_pull = pulls[0] if pulls else None
        event_hooks.append(hook)

    durability_runs = (
        DurabilityRun.objects
        .filter(event=event)
        .select_related("team", "tractor")
        .order_by("-total_laps", "run_order")
    )

    maneuverability_runs = (
        ManeuverabilityRun.objects
        .filter(event=event)
        .select_related("team")
        .order_by("run_order")
    )

    context = {
        "event": event,
        "event_teams": event_teams,
        "rankings_by_class": rankings_by_class,
        "event_hooks": event_hooks,
        "durability_runs": durability_runs,
        "maneuverability_runs": maneuverability_runs,
        "active_page": "events",
        "schedule_items":schedule_items,
    }
    return render(request, "events/event_detail.html", context)

@log_view
@cache_page(300)
def pull_detail(request, pull_id):
    pull = (
        Pull.objects
        .select_related("team", "event")
        .get(pk=pull_id)
    )

    # PullData rows for this pull, ordered by distance (or whatever you used before)
    data_qs = (
        PullData.objects
        .filter(pull=pull)
        .order_by("distance")   # adjust if you had a different order
    )

    distances = []
    speeds = []
    forces = []

    for row in data_qs:
        # guard against None
        if row.distance is None or row.speed is None or row.chain_force is None:
            continue
        distances.append(float(row.distance))
        speeds.append(float(row.speed))
        forces.append(float(row.chain_force))

    has_data = bool(distances) and bool(speeds) and bool(forces)

    pull_name=pull.team.team_abbreviation+" " + pull.hook.hook_name
    #media=PullMedia.objects.filter(pull_media_type=PullMedia.types.YOUTUBE_VIDEO)
    #print(media)
    yt_vids = PerformanceEventMedia.objects.filter(
        performance_event_type=PerformanceEventMedia.EventTypes.PULL,
        performance_event_id=pull.pull_id,
        media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
    )
    if not yt_vids.exists():
        yt_vids = pull.pull_media.all().filter(pull_media_type=PullMedia.types.YOUTUBE_VIDEO)
    #print(yt_vids)
    context = {
        "yt_embed":yt_vids,
        "pull_name":pull_name,
        "pull": pull,
        "has_data": has_data,
        "distances_json": json.dumps(distances),
        "speeds_json": json.dumps(speeds),
        "forces_json": json.dumps(forces),
        "active_page": "events",  # or None if you don't want nav highlight
    }

    return render(request, "events/pull_detail.html", context)

@log_view
@cache_page(300)
def durability_run_detail(request, run_id: int):
    durability_run = (
        DurabilityRun.objects
        .select_related("team", "event", "tractor")
        .get(pk=run_id)
    )

    data_qs = (
        DurabilityData.objects
        .filter(durability_run=durability_run)
        .order_by("durability_data_id")
        .only("durability_data_id", "speed", "pressure", "power")
    )

    rows = list(data_qs)

    x_values = []
    speeds = []
    pressures = []
    powers = []

    for idx, row in enumerate(rows):
        if row.speed is None or row.pressure is None or row.power is None:
            continue
        x_values.append(float(idx))
        speeds.append(float(row.speed))
        pressures.append(float(row.pressure))
        powers.append(float(row.power))

    total_points = len(x_values)
    max_points = 5000
    sampled = False

    if total_points > max_points and max_points > 0:
        step = (total_points // max_points) + 1
        x_values = x_values[::step]
        speeds = speeds[::step]
        pressures = pressures[::step]
        powers = powers[::step]
        sampled = True

    has_data = bool(x_values) and bool(speeds) and bool(pressures) and bool(powers)
    table_rows = list(zip(x_values, speeds, pressures, powers))

    yt_vids = PerformanceEventMedia.objects.filter(
        performance_event_type=PerformanceEventMedia.EventTypes.DURABILITY,
        performance_event_id=durability_run.durability_run_id,
        media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
    )

    context = {
        "durability_run": durability_run,
        "yt_embed": yt_vids,
        "has_data": has_data,
        "sampled": sampled,
        "total_points": total_points,
        "shown_points": len(x_values),
        "x_label": "Sample #",
        "x_values_json": json.dumps(x_values),
        "speeds_json": json.dumps(speeds),
        "pressures_json": json.dumps(pressures),
        "powers_json": json.dumps(powers),
        "table_rows": table_rows,
        "active_page": "events",
    }

    return render(request, "events/durability_run_detail.html", context)

@log_view
@cache_page(300)
def maneuverability_run_detail(request, run_id: int):
    maneuverability_run = (
        ManeuverabilityRun.objects
        .select_related("team", "event")
        .get(pk=run_id)
    )

    yt_vids = PerformanceEventMedia.objects.filter(
        performance_event_type=PerformanceEventMedia.EventTypes.MANEUVERABILITY,
        performance_event_id=maneuverability_run.maneuverability_run_id,
        media_type=PerformanceEventMedia.MediaTypes.YOUTUBE_VIDEO,
    )

    context = {
        "maneuverability_run": maneuverability_run,
        "yt_embed": yt_vids,
        "active_page": "events",
    }

    return render(request, "events/maneuverability_run_detail.html", context)

@log_view
@cache_page(300)
def tractor_detail(request, tractor_id):
    # Grab the tractor, along with its original_team and all TractorEvent rows
    tractor = get_object_or_404(
        Tractor.objects
        .select_related("original_team")
        .prefetch_related(
            Prefetch(
                "tractor_events",
                queryset=TractorEvent.objects.select_related("event", "team"),
            )
        ),
        pk=tractor_id,
    )

    # All pulls for this tractor, with event/team/hook info
    pulls = (
        Pull.objects
        .filter(tractor=tractor)
        .select_related("event", "team", "hook")
        .order_by("event__event_datetime", "pull_id")
    )

    # Distinct events this tractor has appeared in (via TractorEvent / pulls)
    events = (
        Event.objects
        .filter(tractor_events__tractor=tractor)
        .distinct()
        .order_by("event_datetime")
    )

    # Distinct teams that have used this tractor
    teams = (
        Team.objects
        .filter(tractor_events__tractor=tractor)
        .distinct()
        .order_by("team_name")
    )

    # Usages table for the "Teams & Years Used" card.
    # There is no "year" field, so we derive year from event.event_datetime.year.
    tractor_events = (
        TractorEvent.objects
        .filter(tractor=tractor)
        .select_related("team", "event")
        .order_by("event__event_datetime", "team__team_name")
    )

    instagram=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.INSTAGRAM).first()
    facebook=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.FACEBOOK).first()
    linkedin=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.LINKEDIN).first()
    bio=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.BIO).first()
    website=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.WEBSITE).first()
    youtube=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.YOUTUBE).first()
    nickname=TractorInfo.objects.filter(tractor=tractor,info_type=TractorInfo.InfoTypes.NICKNAME).first()


    usages = []
    for te in tractor_events:
        if te.event and te.event.event_datetime:
            year = te.event.event_datetime.year
        else:
            year = None
        usages.append({
            "team": te.team,
            "event": te.event,
            "year": year,
        })

    # Photos: EventTeamPhoto -> EventTeam (event, team).
    # We want photos where the (event, team) pair matches a TractorEvent for this tractor.
    #This line does not work, it needs to specfically look for photos where this tractor was present and look for the team that it represented.
    #This presents a bug with A/X teams

    photo_filter = Q()
    for te in tractor_events:
        photo_filter |= Q(
            event_team__event=te.event,
            event_team__team=te.team,
        )

    tractor_photos = (
        EventTeamPhoto.objects
        .filter(photo_filter)
        .select_related("event_team__event","event_team__team")
        .distinct()
        .order_by("created_at")
    )

    for te in tractor_events:
        photos=EventTeamPhoto.objects.filter(event_team__event=te.event,event_team__team=te.team)

    # Get tractor-specific media (images)
    tractor_media = (
        TractorMedia.objects
        .filter(tractor=tractor, approved=True, media_type=TractorMedia.MediaTypes.IMAGE)
        .select_related("uploaded_by")
        .order_by("-created_at")
    )

    context = {
        "tractor": tractor,
        "pulls": pulls,
        "events": events,
        "teams": teams,
        "usages": usages,
        "tractor_photos": tractor_photos,
        "tractor_media": tractor_media,
        "active_page": "tractors",
        "nickname":nickname,
        "website":website,
        "bio":bio
    }
    return render(request, "events/tractor_detail.html", context)

def durability_event_results(request, event_id: int):
    event = get_object_or_404(Event, event_id=event_id)

    runs = (
        DurabilityRun.objects
        .filter(event=event)
        .select_related("team", "tractor", "event")
        .order_by(
            "-total_laps",
            "run_order",
            "team__team_name",
            "tractor__tractor_name"
        )
    )

    # Optional: assign ranks only to runs with laps recorded
    ranked_rows = []
    rank = 0
    for r in runs:
        if r.total_laps is not None and r.total_laps > 0:
            rank += 1
            display_rank = rank
        else:
            display_rank = None
        ranked_rows.append((display_rank, r))

    return render(
        request,
        "events/durability_event_results.html",
        {
            "event": event,
            "ranked_rows": ranked_rows,
        },
    )

# def team_detail(request, team_id):
#     team = get_object_or_404(Team, team_id=team_id)

#     # Fetch all infos for this team once
#     infos = TeamInfo.objects.filter(team=team, info_type__in=INFO_MAP.values())
#     info_by_type = {ti.info_type: ti for ti in infos}

#     context = {
#         "team": team,
#         "can_edit": can_edit_team(request.user, team),

#         # match your template variables
#         "nickname": info_by_type.get(TeamInfo.InfoTypes.NICKNAME),
#         "bio": info_by_type.get(TeamInfo.InfoTypes.BIO),
#         "website": info_by_type.get(TeamInfo.InfoTypes.WEBSITE),
#         "instagram": info_by_type.get(TeamInfo.InfoTypes.INSTAGRAM),
#         "facebook": info_by_type.get(TeamInfo.InfoTypes.FACEBOOK),
#         "linkedin": info_by_type.get(TeamInfo.InfoTypes.LINKEDIN),
#         "youtube": info_by_type.get(TeamInfo.InfoTypes.YOUTUBE),

#         # keep your existing stuff too (event_teams, team_photos, chart_*, etc.)
#         # ...
#     }
#     return render(request, "events/team_detail.html", context)

def _initial_from_teaminfo(team):
    qs = TeamInfo.objects.filter(team=team, info_type__in=INFO_MAP.values())
    by_type = {row.info_type: row.info for row in qs}
    return {
        key: by_type.get(int(info_type), "")
        for key, info_type in INFO_MAP.items()
    }

def _upsert_teaminfo(team, info_type, value: str):
    value = (value or "").strip()

    # If blank => delete any existing row(s) for tidiness
    if value == "":
        TeamInfo.objects.filter(team=team, info_type=int(info_type)).delete()
        return

    # If you have unique(team, info_type) this will be 0/1 rows; if not, we normalize:
    qs = TeamInfo.objects.filter(team=team, info_type=int(info_type)).order_by("team_info_id")
    existing = qs.first()

    if existing:
        # delete any accidental duplicates
        qs.exclude(team_info_id=existing.team_info_id).delete()
        existing.info = value
        existing.save(update_fields=["info"])
    else:
        TeamInfo.objects.create(team=team, info_type=int(info_type), info=value)

@login_required
def team_profile_edit(request, team_id: int):
    team = get_object_or_404(Team, team_id=team_id)

    if not can_edit_team(request.user, team):
        raise PermissionDenied

    if request.method == "POST":
        form = TeamProfileEditForm(request.POST)
        if form.is_valid():
            for field_name, info_type in INFO_MAP.items():
                _upsert_teaminfo(team, info_type, form.cleaned_data.get(field_name, ""))

            messages.success(request, "Team profile updated.")
            return redirect("events:team_detail", team.team_id)
    else:
        form = TeamProfileEditForm(initial=_initial_from_teaminfo(team))

    return render(request, "events/team_profile_edit.html", {
        "team": team,
        "form": form,
    })

def _tractor_initial(tractor):
    qs = TractorInfo.objects.filter(
        tractor=tractor,
        info_type__in=TRACTOR_INFO_MAP.values(),
    )
    by_type = {row.info_type: row.info for row in qs}
    return {k: by_type.get(int(t), "") for k, t in TRACTOR_INFO_MAP.items()}

def _tractor_upsert(tractor, info_type, value: str):
    value = (value or "").strip()

    if value == "":
        TractorInfo.objects.filter(tractor=tractor, info_type=int(info_type)).delete()
        return

    qs = TractorInfo.objects.filter(tractor=tractor, info_type=int(info_type)).order_by("tractor_info_id")
    existing = qs.first()

    if existing:
        qs.exclude(tractor_info_id=existing.tractor_info_id).delete()
        existing.info = value
        existing.save(update_fields=["info"])
    else:
        TractorInfo.objects.create(tractor=tractor, info_type=int(info_type), info=value)

@login_required
def tractor_profile_edit(request, tractor_id: int):
    tractor = get_object_or_404(Tractor, tractor_id=tractor_id)

    if not can_edit_tractor(request.user, tractor):
        raise PermissionDenied  # shows your 403 template

    # Load existing photos for selection
    existing_photos = (
        TractorMedia.objects
        .filter(tractor=tractor, approved=True, media_type=TractorMedia.MediaTypes.IMAGE)
        .order_by("-created_at")
    )

    if request.method == "POST":
        form = TractorProfileEditForm(request.POST)
        if form.is_valid():
            for field_name, info_type in TRACTOR_INFO_MAP.items():
                _tractor_upsert(tractor, info_type, form.cleaned_data.get(field_name, ""))

            # Handle primary photo selection
            primary_photo_id = request.POST.get("primary_photo")
            if primary_photo_id:
                if primary_photo_id == "none":
                    tractor.primary_photo = None
                else:
                    try:
                        media = TractorMedia.objects.get(
                            media_id=int(primary_photo_id),
                            tractor=tractor,
                            approved=True,
                            media_type=TractorMedia.MediaTypes.IMAGE
                        )
                        tractor.primary_photo = media
                    except (TractorMedia.DoesNotExist, ValueError):
                        messages.error(request, "Invalid primary photo selection.")
                tractor.save()

            # Handle photo upload if present
            photo_file = request.FILES.get("photo")
            if photo_file and photo_file.name:
                approved = request.user.has_perm("events.can_auto_approve_tractor_media")

                # Get client IP
                xff = request.META.get("HTTP_X_FORWARDED_FOR")
                ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")

                filename = photo_file.name

                # Validate file extension (reuses existing allowed_file function)
                if allowed_file(filename):
                    # Sanitize filename
                    name_root, ext = os.path.splitext(filename)
                    ext = ext.lower()
                    safe_root = "".join(c for c in name_root if c.isalnum() or c in ("-", "_"))
                    if not safe_root:
                        safe_root = "photo"

                    filename = f"tractor{tractor_id}_{safe_root}{ext}"
                    save_path = Path(f"/var/www/quarterscale/static/photos/{filename}")
                    save_path.parent.mkdir(parents=True, exist_ok=True)

                    with save_path.open("wb+") as dest:
                        for chunk in photo_file.chunks():
                            dest.write(chunk)

                    # Create database record using PerformanceEventMedia pattern
                    rel_path = f"photos/{filename}"
                    TractorMedia.objects.create(
                        tractor=tractor,
                        media_type=TractorMedia.MediaTypes.IMAGE,
                        link=rel_path,
                        uploaded_by=request.user,
                        submitted_from_ip=ip,
                        approved=approved,
                    )
                    messages.success(request, "Photo uploaded successfully!")
                else:
                    messages.error(request, "Invalid file type. Please upload an image (png, jpg, jpeg, gif, webp).")

            messages.success(request, "Tractor profile updated.")
            return redirect("events:tractor_detail", tractor.tractor_id)
    else:
        form = TractorProfileEditForm(initial=_tractor_initial(tractor))

    return render(request, "events/tractor_profile_edit.html", {
        "tractor": tractor,
        "form": form,
        "existing_photos": existing_photos,
    })
