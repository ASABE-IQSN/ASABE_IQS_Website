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
from .models import TeamClass, Team,PullMedia, EventTeamPhoto, EventTeam, Pull, Event, Hook, PullData, Tractor, TractorEvent, ScheduleItem
from django.views.decorators.http import require_POST
from django.contrib import messages
from functools import wraps
from django.http import HttpRequest, HttpResponse
from iqs_site.utilities import log_view
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt

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
    tractors = Tractor.objects.select_related("original_team").order_by("tractor_name")

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
def team_detail(request, team_id):
    team = get_object_or_404(Team, pk=team_id)

    # All event-team rows for this team (with events preloaded)
    event_teams = (
        EventTeam.objects
        .select_related("event", "team")
        .filter(team=team)
        .order_by("event__event_datetime")
    )

    # Photos for this team (approved only), newest first
    team_photos = (
        EventTeamPhoto.objects
        .select_related("event_team__event")
        .filter(event_team__team=team, approved=True)
        .order_by("-event_team_photo_id")
    )

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

    context = {
        "event": event,
        "event_teams": event_teams,
        "rankings_by_class": rankings_by_class,
        "event_hooks": event_hooks,
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
    yt_vids=pull.pull_media.all().filter(pull_media_type=PullMedia.types.YOUTUBE_VIDEO)
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



    context = {
        "tractor": tractor,
        "pulls": pulls,
        "events": events,
        "teams": teams,
        "usages": usages,
        "tractor_photos": tractor_photos,
        "active_page": "tractors",
    }
    return render(request, "events/tractor_detail.html", context)