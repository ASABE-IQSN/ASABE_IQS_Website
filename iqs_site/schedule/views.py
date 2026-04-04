import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from events.models import Event, Team

from .models import (
    Location,
    ScheduleItem,
    ScheduleItemType,
    ScheduleNotification,
    ScheduleSubscription,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_teams(user):
    """Return all Team objects the user belongs to via their Django groups."""
    return Team.objects.filter(
        group_profile__group__user=user,
    ).select_related("group_profile")


def _locations_geojson(event):
    """Return a list of location dicts suitable for Leaflet."""
    locs = Location.objects.filter(event=event)
    return [
        {
            "id": loc.location_id,
            "name": loc.name,
            "description": loc.description or "",
            "address": loc.address or "",
            "lat": loc.latitude,
            "lng": loc.longitude,
            "icon_category": loc.icon_category,
            "icon_label": loc.get_icon_category_display(),
        }
        for loc in locs
    ]


# ── Public views ──────────────────────────────────────────────────────────────

def event_schedule(request, event_id):
    """Full event schedule — public, all teams."""
    event = get_object_or_404(Event, pk=event_id)
    schedule_items = (
        ScheduleItem.objects
        .select_related("type", "team", "location")
        .filter(event=event)
        .order_by("datetime")
    )
    locations_json = json.dumps(_locations_geojson(event))
    return render(request, "schedule/event_schedule.html", {
        "event": event,
        "schedule_items": schedule_items,
        "locations_json": locations_json,
        "active_page": "events",
    })


def locations_api(request, event_id):
    """JSON endpoint returning all locations for an event (used by Leaflet)."""
    event = get_object_or_404(Event, pk=event_id)
    return JsonResponse(_locations_geojson(event), safe=False)


# ── Authenticated team view ───────────────────────────────────────────────────

@login_required
def team_schedule(request, event_id):
    """Show the logged-in user's team schedule for a specific event."""
    event = get_object_or_404(Event, pk=event_id)

    teams = list(_user_teams(request.user))

    if not teams:
        return render(request, "schedule/team_schedule.html", {
            "event": event,
            "no_team": True,
            "active_page": "events",
        })

    # If user is on multiple teams, prefer one specified by ?team=<id>
    team_id_param = request.GET.get("team")
    if team_id_param:
        team = next((t for t in teams if str(t.pk) == team_id_param), teams[0])
    else:
        team = teams[0]

    schedule_items = (
        ScheduleItem.objects
        .select_related("type", "location")
        .filter(event=event, team=team)
        .order_by("datetime")
    )

    # Subscriptions for this user + team (for highlighting)
    subscriptions = ScheduleSubscription.objects.filter(
        user=request.user, team=team
    ).select_related("schedule_item_type")
    subscribed_type_ids = set(
        s.schedule_item_type_id for s in subscriptions
        if s.schedule_item_type_id is not None
    )
    subscribed_all = subscriptions.filter(schedule_item_type__isnull=True).exists()

    unread_notifications = (
        ScheduleNotification.objects
        .filter(user=request.user, is_read=False)
        .select_related("schedule_item__type")
        .order_by("-created_at")[:10]
    )

    locations_json = json.dumps(_locations_geojson(event))

    return render(request, "schedule/team_schedule.html", {
        "event": event,
        "team": team,
        "teams": teams,
        "schedule_items": schedule_items,
        "subscriptions": subscriptions,
        "subscribed_type_ids": subscribed_type_ids,
        "subscribed_all": subscribed_all,
        "unread_notifications": unread_notifications,
        "unread_count": ScheduleNotification.objects.filter(
            user=request.user, is_read=False
        ).count(),
        "locations_json": locations_json,
        "active_page": "events",
    })


# ── Subscriptions ─────────────────────────────────────────────────────────────

@login_required
def manage_subscriptions(request):
    """Subscribe / unsubscribe from team+type combinations."""
    teams = list(_user_teams(request.user))
    item_types = list(ScheduleItemType.objects.all().order_by("name"))

    if request.method == "POST":
        action = request.POST.get("action")  # "subscribe" or "unsubscribe"
        team_id = request.POST.get("team_id")
        type_id = request.POST.get("type_id") or None  # empty → all types

        team = get_object_or_404(Team, pk=team_id)

        # Verify the requesting user belongs to this team or is staff
        if not request.user.is_staff and team not in teams:
            return JsonResponse({"error": "Not your team"}, status=403)

        type_obj = None
        if type_id:
            type_obj = get_object_or_404(ScheduleItemType, pk=type_id)

        if action == "subscribe":
            ScheduleSubscription.objects.get_or_create(
                user=request.user,
                team=team,
                schedule_item_type=type_obj,
            )
        elif action == "unsubscribe":
            ScheduleSubscription.objects.filter(
                user=request.user,
                team=team,
                schedule_item_type=type_obj,
            ).delete()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True})

    existing_subs = (
        ScheduleSubscription.objects
        .filter(user=request.user)
        .select_related("team", "schedule_item_type")
        .order_by("team__team_name", "schedule_item_type__name")
    )

    recent_notifications = (
        ScheduleNotification.objects
        .filter(user=request.user)
        .select_related("schedule_item__type", "schedule_item__team")
        .order_by("-created_at")[:20]
    )

    return render(request, "schedule/subscriptions.html", {
        "teams": teams,
        "item_types": item_types,
        "existing_subs": existing_subs,
        "recent_notifications": recent_notifications,
        "active_page": "events",
    })


# ── Notification actions ──────────────────────────────────────────────────────

@login_required
@require_POST
def mark_notification_read(request, notif_id):
    """Mark a single notification as read. Returns JSON."""
    notif = get_object_or_404(
        ScheduleNotification, pk=notif_id, user=request.user
    )
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all of the user's unread notifications as read."""
    ScheduleNotification.objects.filter(
        user=request.user, is_read=False
    ).update(is_read=True)
    return JsonResponse({"ok": True})
